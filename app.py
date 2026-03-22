import streamlit as st
import polars as pl
import io
from datetime import datetime

st.set_page_config(page_title="Reporte de Ingresos", layout="centered")
st.title("📊 Reporte de Ingresos")

archivo = st.file_uploader("Sube tu archivo .xlsx", type=["xlsx"])

if archivo:
    try:
        # 1. Leer Excel
        df = pl.read_excel(archivo, read_options={"header_row": 4})
        
        COL_TRANSACCION = "Tipo de Transacción"
        COL_MONTO = "Monto"
        COL_FECHA = "Fecha de operación" if "Fecha de operación" in df.columns else "Fecha"

        # Limpiar Monto
        df = df.with_columns(
            pl.col(COL_MONTO).cast(pl.String).str.replace_all(r"[^\d.]", "").cast(pl.Float64).fill_null(0)
        )

        # Filtrar "TE PAGÓ" y parsear Fecha
        df_ingresos = df.filter(pl.col(COL_TRANSACCION).str.strip_chars() == "TE PAGÓ")
        df_ingresos = df_ingresos.with_columns(
            pl.col(COL_FECHA).str.to_date(format="%d/%m/%Y %H:%M:%S", strict=False)
        ).filter(pl.col(COL_FECHA).is_not_null())

        if df_ingresos.is_empty():
            st.warning("No hay ingresos registrados con 'TE PAGÓ' en el archivo.")
        else:
            # --- FORMATO DE FILTRO ---
            meses_espanol = {
                "1": "Enero", "2": "Febrero", "3": "Marzo", "4": "Abril",
                "5": "Mayo", "6": "Junio", "7": "Julio", "8": "Agosto",
                "9": "Septiembre", "10": "Octubre", "11": "Noviembre", "12": "Diciembre"
            }

            df_ingresos = df_ingresos.with_columns([
                pl.col(COL_FECHA).dt.month().cast(pl.String).replace(meses_espanol).alias("Mes_Nombre"),
                pl.col(COL_FECHA).dt.strftime("%y").alias("Anio_Corto")
            ]).with_columns(
                (pl.col("Mes_Nombre") + " " + pl.col("Anio_Corto")).alias("Mes_Anio")
            )

            meses_disponibles = (
                df_ingresos.sort(COL_FECHA, descending=True)
                .select("Mes_Anio").unique(maintain_order=True)
                .to_series().to_list()
            )

            mes_actual_num = str(datetime.now().month)
            anio_actual_corto = datetime.now().strftime("%y")
            mes_actual_str = f"{meses_espanol[mes_actual_num]} {anio_actual_corto}"
            
            opciones_filtro = ["Todos"] + meses_disponibles
            
            indice_por_defecto = opciones_filtro.index(mes_actual_str) if mes_actual_str in opciones_filtro else 0

            mes_seleccionado = st.selectbox(
                "📅 Filtrar por Mes:", 
                options=opciones_filtro, 
                index=indice_por_defecto
            )

            if mes_seleccionado == "Todos":
                df_filtrado = df_ingresos
                titulo_metric = "TOTAL RECAUDADO (Histórico)"
            else:
                df_filtrado = df_ingresos.filter(pl.col("Mes_Anio") == mes_seleccionado)
                titulo_metric = f"TOTAL RECAUDADO ({mes_seleccionado})"

            if df_filtrado.is_empty():
                st.info("No hay datos para la selección actual.")
            else:
                # 1. TOTAL AL INICIO
                total_final = round(df_filtrado.select(pl.col(COL_MONTO)).sum().item(), 2)
                st.metric(label=f"💰 {titulo_metric}", value=f"S/.{total_final:,.2f}")
                st.divider()

                # 2. AGRUPACIÓN Y TOTAL
                resumen_diario = (
                    df_filtrado
                    .group_by(COL_FECHA)
                    .agg(pl.col(COL_MONTO).sum().round(2).alias("Ingreso Diario"))
                    .sort(COL_FECHA, descending=False)
                )

                resumen_diario = resumen_diario.with_columns(
                    pl.col(COL_FECHA).dt.strftime("%d/%m/%Y")
                )
                
                fila_total = pl.DataFrame({
                    COL_FECHA: ["     *TOTAL*   "], # Le ponemos negritas en markdown al texto TOTAL
                    "Ingreso Diario": [total_final]
                })
                
                resumen_diario_con_total = pl.concat([resumen_diario, fila_total])

                # 3. TABLA VISUAL
                st.subheader("📋 Detalle de Ingresos")
                st.dataframe(
                    resumen_diario_con_total, 
                    width='stretch',
                    column_config={
                        "Ingreso Diario": st.column_config.NumberColumn("Suma del Día (S/.)", format="S/. %.2f")
                    }
                )

                # 4. VALORES PARA COPIAR EN FORMATO MARKDOWN
                st.caption("✨ Toca el ícono en la esquina superior derecha del recuadro para copiar la tabla (Formato Markdown):")
                
                # Construimos la tabla Markdown manualmente fila por fila
                lineas_md = ["|      Fecha     |   Ingreso  |", "| ---------- | -------- |"]
                for row in resumen_diario_con_total.iter_rows():
                    fecha_str = str(row[0])
                    # Le damos formato de moneda (ej. S/.1,250.00)
                    monto_str = f"S/.{row[1]:,.2f}"
                    
                    # Si es la fila final, ponemos el monto en negritas también
                    if fecha_str == "     *TOTAL*   ":
                        monto_str = f"*{monto_str}*"
                        
                    lineas_md.append(f"| {fecha_str} | {monto_str} |")
                
                texto_copiar = "\n".join(lineas_md)
                
                # Le indicamos a Streamlit que el lenguaje es markdown para que lo resalte bonito
                st.code(texto_copiar, language="markdown")

                # 5. BOTÓN DESCARGAR EXCEL
                buffer = io.BytesIO()
                # Quitamos los asteriscos de markdown solo para el Excel
                resumen_diario_excel = resumen_diario_con_total.with_columns(
                    pl.col(COL_FECHA).str.replace_all(r"\*", "")
                )
                resumen_diario_excel.to_pandas().to_excel(buffer, index=False, engine='xlsxwriter')
                
                nombre_archivo = "ingresos_historico.xlsx" if mes_seleccionado == "Todos" else f"ingresos_{mes_seleccionado.replace(' ', '_')}.xlsx"
                
                st.download_button(
                    label="📥 Descargar Tabla en Excel (.xlsx)",
                    data=buffer.getvalue(),
                    file_name=nombre_archivo,
                    mime="application/vnd.ms-excel",
                    width='stretch'
                )

    except Exception as e:
        st.error(f"Error procesando el archivo: {e}")
else:
    st.info("Sube el archivo Excel para procesar tus datos.")