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
        # Usa read_options={"header_row": 4} si hay filas vacías al inicio del excel real
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
            # --- NUEVO FORMATO DE FILTRO CORREGIDO ---
            # Ahora las llaves son texto ("1" en vez de 1)
            meses_espanol = {
                "1": "Enero", "2": "Febrero", "3": "Marzo", "4": "Abril",
                "5": "Mayo", "6": "Junio", "7": "Julio", "8": "Agosto",
                "9": "Septiembre", "10": "Octubre", "11": "Noviembre", "12": "Diciembre"
            }

            # 1. Casteamos el mes a String antes de reemplazar
            df_ingresos = df_ingresos.with_columns([
                pl.col(COL_FECHA).dt.month().cast(pl.String).replace(meses_espanol).alias("Mes_Nombre"),
                pl.col(COL_FECHA).dt.strftime("%y").alias("Anio_Corto")
            ]).with_columns(
                (pl.col("Mes_Nombre") + " " + pl.col("Anio_Corto")).alias("Mes_Anio")
            )

            # Obtener lista única manteniendo el orden del más reciente al antiguo
            meses_disponibles = (
                df_ingresos.sort(COL_FECHA, descending=True)
                .select("Mes_Anio").unique(maintain_order=True)
                .to_series().to_list()
            )

            # Determinar el mes actual para el valor por defecto
            mes_actual_num = str(datetime.now().month) # Lo pasamos a texto aquí también
            anio_actual_corto = datetime.now().strftime("%y")
            mes_actual_str = f"{meses_espanol[mes_actual_num]} {anio_actual_corto}"
            
            opciones_filtro = ["Todos"] + meses_disponibles
            
            if mes_actual_str in opciones_filtro:
                indice_por_defecto = opciones_filtro.index(mes_actual_str)
            else:
                indice_por_defecto = 0 

            # Renderizar el Filtro
            mes_seleccionado = st.selectbox(
                "📅 Filtrar por Mes:", 
                options=opciones_filtro, 
                index=indice_por_defecto
            )

            # Aplicar Filtro
            if mes_seleccionado == "Todos":
                df_filtrado = df_ingresos
                titulo_metric = "TOTAL RECAUDADO (Histórico)"
            else:
                df_filtrado = df_ingresos.filter(pl.col("Mes_Anio") == mes_seleccionado)
                titulo_metric = f"TOTAL RECAUDADO ({mes_seleccionado})"

            if df_filtrado.is_empty():
                st.info("No hay datos para la selección actual.")
            else:
                # 1. TOTAL AL INICIO (Redondeado a 2 decimales)
                total_final = round(df_filtrado.select(pl.col(COL_MONTO)).sum().item(), 2)
                st.metric(label=f"💰 {titulo_metric}", value=f"S/.{total_final:,.2f}")
                st.divider()

                # Lógica: Agrupar por fecha, redondear la suma y ordenar
                resumen_diario = (
                    df_filtrado
                    .group_by(COL_FECHA)
                    .agg(pl.col(COL_MONTO).sum().round(2).alias("Ingreso Diario")) # REDONDEO AQUÍ
                    .sort(COL_FECHA, descending=False)
                )

                # --- AÑADIR LA FILA "TOTAL" ---
                resumen_diario = resumen_diario.with_columns(
                    pl.col(COL_FECHA).dt.strftime("%d/%m/%Y")
                )
                
                fila_total = pl.DataFrame({
                    COL_FECHA: ["TOTAL"],
                    "Ingreso Diario": [total_final]
                })
                
                resumen_diario_con_total = pl.concat([resumen_diario, fila_total])
                # ------------------------------

                # 2. TABLA VISUAL
                st.subheader("📋 Detalle de Ingresos")
                st.dataframe(
                    resumen_diario_con_total, 
                    use_container_width=True,
                    column_config={
                        "Ingreso Diario": st.column_config.NumberColumn("Suma del Día (S/.)", format="S/. %.2f")
                    }
                )

                # 3. VALORES PARA COPIAR (Limpios y redondeados)
                st.caption("✨ Toca el ícono en la esquina superior derecha del recuadro para copiar los datos:")
                texto_copiar = resumen_diario_con_total.to_pandas().to_csv(sep='\t', index=False)
                st.code(texto_copiar, language="text")

                # 4. BOTÓN DESCARGAR EXCEL
                buffer = io.BytesIO()
                resumen_diario_con_total.to_pandas().to_excel(buffer, index=False, engine='xlsxwriter')
                
                nombre_archivo = "ingresos_historico.xlsx" if mes_seleccionado == "Todos" else f"ingresos_{mes_seleccionado.replace(' ', '_')}.xlsx"
                
                st.download_button(
                    label="📥 Descargar Tabla en Excel (.xlsx)",
                    data=buffer.getvalue(),
                    file_name=nombre_archivo,
                    mime="application/vnd.ms-excel",
                    use_container_width=True
                )

    except Exception as e:
        st.error(f"Error procesando el archivo: {e}")
else:
    st.info("Sube el archivo Excel para procesar tus datos.")