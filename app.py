# script para generar los archivos de montos, sucursales y ventas a partir del archivo de ventas original
# como usar => primero descargar el file de tibco, cambiar el nombre a "Ventas_Rango_de_fechas.xls" 
# moverlo a la carpeta ventas_mod, luego abrir el archivo en excel y eliminar la primera fila y cambiar la columna monto a enteros, 
# sin decimales, luego ejecutar este script. Se generarán los archivos montos.csv, sucursales.csv y ventas.csv en la carpeta ventas_mod


import pandas as pd
import xlrd
import typer, json
import sys
from openpyxl import load_workbook


app = typer.Typer()




@app.command()
def ventas():
    """
    1 ==> Crea las tablas en formato .csv de ventas, sucursales y montos
    """
    try:

        df = pd.read_excel('ventas_mod/Ventas_Rango_de_fechas.xls')
        pd.set_option('display.width', None)
        pd.set_option('display.max_columns', None)
        pd.set_option('display.max_colwidth', None)
        pd.set_option('display.max_rows', None)
        

        for col in ['FAMILIA', 'PRODUCTO', 'VARIACION']:
            df[col] = df[col].astype(str).str.strip().str.replace(r'\s+', ' ', regex=True)

        montos = df.copy()
        sucursales = df.copy()
        ventas = df.copy()

        # tabla de montos
        montos = montos.drop(columns=['SUCURSAL', 'CANTIDAD']).groupby(['FAMILIA', 'PRODUCTO', 'VARIACION'], dropna=False)['MONTO'].sum().reset_index()
        #display(montos)


        #tabla de sucursales
        columnas_table_sucursales = [col for col in df.columns if col not in ['SUCURSAL', 'MONTO']]
        sucursales = sucursales.drop(columns=columnas_table_sucursales).groupby('SUCURSAL', dropna=False).sum().reset_index()
        #display(sucursales)



        ## tabla de ventas por sucursal
        columnas_index = [col for col in ventas.columns if col not in ['SUCURSAL', 'CANTIDAD']]
        for col in columnas_index:
            ventas[col] = ventas[col].fillna('SIN DATO')

        ventas = ventas.pivot_table(index=columnas_index, columns='SUCURSAL', values='CANTIDAD', aggfunc='sum', fill_value=0).reset_index()
        ventas = ventas.drop(columns=['MONTO'])

        for col in ['FAMILIA', 'PRODUCTO', 'VARIACION']:
            ventas[col] = ventas[col].astype(str).str.strip().str.replace(r'\s+', ' ', regex=True)

        columnas_ventas = [col for col in ventas.columns if col not in ['FAMILIA', 'PRODUCTO', 'VARIACION']]
        columnas_identificadoras = ['FAMILIA', 'PRODUCTO', 'VARIACION']
        ventas = ventas.groupby(columnas_identificadoras, dropna=False)[columnas_ventas].sum().reset_index()

        ventas.columns.name = None   # <- elimina el "SUCURSAL" fantasma en el índice
        ventas[['FAMILIA', 'PRODUCTO', 'VARIACION']] = ventas[['FAMILIA', 'PRODUCTO', 'VARIACION']].replace('SIN DATO', pd.NA)


        ventas = ventas.rename(columns={'C.C. TITAN': 'TITAN', 'CC PARQUE COLINA': 'COLINA'})

        ventas = ventas.merge(montos, on=['FAMILIA', 'PRODUCTO', 'VARIACION'], how='left')
        ventas = ventas.rename(columns={'MONTO': 'VALOR'})
        ventas['VALOR'] = ventas['VALOR'].astype('Int64')
        #display(ventas)
        montos.to_csv('ventas_mod/montos.csv', sep='|', index=False)
        sucursales.to_csv('ventas_mod/sucursales.csv', sep='|', index=False)
        ventas.to_csv('ventas_mod/ventas.csv', sep='|', index=False)

        print("\nArchivos montos.csv, sucursales.csv y ventas.csv generados correctamente. 👍")
    except Exception as e:
        print(f"Error: {e} 🤮")



@app.command()
def merge():
    """
    2 ==> Unir las tablas ventas con stock >> resultado/resultado.csv
    """

    # script para generar el archivo resultado.csv a partir de los archivos ventas.csv y test_stock.txt
    # este debe ser nombre de las columnas del archivo stock.txt debe ser el mismo que el de las columnas del archivo ventas.csv, 
    # excepto por la columna valor que solo está en ventas.csv

    try:
        columnas_file_ventas = [
            'familia',
            'producto',
            'variacion',
            'salitre',
            'andino',
            'titan',
            'colina',
            'santafe',
            'chia',
            'calle 79',
            'calle 109',
            'calle 122',
            'cedritos',
            'fabrica',
            'valor'
        ]

        columnas_file_stock = [
            'familia',
            'producto',
            'variacion',
            'salitre',
            'andino',
            'titan',
            'colina',
            'santafe',
            'chia',
            'calle 79',
            'calle 109',
            'calle 122',
            'cedritos',
        ]


        sucursales = [
            "salitre",
            "andino",
            "titan",
            "colina",
            "santafe",
            "chia",
            "calle 79",
            "calle 109",
            "calle 122",
            "cedritos"
        ]


        stock = pd.read_csv('test_stock.txt', sep='|')
        ventas = pd.read_csv('ventas_mod/ventas.csv', sep='|')



        ventas.columns = ventas.columns.str.lower()
        stock.columns = stock.columns.str.lower()

        #print(ventas.columns.str.lower())
        #print(columnas_file_ventas)

        if set(ventas.columns.tolist()) != set(columnas_file_ventas):
            raise ValueError("Las columnas del archivo de ventas no coinciden con las esperadas")

        if set(stock.columns.tolist()) != set(columnas_file_stock):
            raise ValueError("Las columnas del archivo de stock no coinciden con las esperadas")



        stock = stock.fillna('.')
        ventas = ventas.fillna('.')
        pd.set_option('display.width', None)
        pd.set_option('display.max_columns', None)
        pd.set_option('display.max_colwidth', None)
        pd.set_option('display.max_rows', None)



        ventas['productos'] = ventas['producto'].str.strip()
        ventas['variacion'] = ventas['variacion'].str.strip()
        ventas['nombre'] = ventas['productos'].str.upper() + ' ' + ventas['variacion'].str.upper()
        ventas['nombre'] = ventas['familia'].str.upper() + ' ' + ventas['producto'].str.upper() + ' ' + ventas['variacion'].str.upper()

        stock['producto'] = stock['producto'].str.strip()
        stock['variacion'] = stock['variacion'].str.strip()
        stock['nombre'] = stock['familia'].str.upper() + ' ' + stock['producto'].str.upper() + ' ' + stock['variacion'].str.upper()


        stock['nombre'] = stock['nombre'].astype(str).str.strip().str.replace(r'\s+', ' ', regex=True)
        ventas['nombre'] = ventas['nombre'].astype(str).str.strip().str.replace(r'\s+', ' ', regex=True)


        stock = stock.rename(
            columns={col: f"{col}_stock" for col in sucursales}
        )
        resultado = pd.merge(
            ventas,
            stock,
            on="nombre",
            how="outer",
            suffixes=("_ventas", "_stock")
        )

        #array de columnas para el resultado final
        columnas = []
        #columnas.append('familia_ventas')
        columnas.append('nombre')
        for sucursal in sucursales:
            
            columnas.append(f"{sucursal}")
            columnas.append(f"{sucursal}_stock")

        columnas.append('fabrica')
        columnas.append('valor')




        for col in resultado.columns:
            if pd.api.types.is_numeric_dtype(resultado[col]):
                resultado[col] = pd.to_numeric(
                    resultado[col], errors='coerce'
                ).round().astype('Int64')

        mask = resultado['familia_ventas'].isna()

        cols_numericas = resultado.select_dtypes(include='number').columns

        resultado.loc[mask, cols_numericas] = (
            resultado.loc[mask, cols_numericas].fillna(0)
        )


        # poner valores vacios en las columnas stock
        sucursales_stock = [f"{i}_stock" for i in sucursales]

        resultado[sucursales_stock] = resultado[sucursales_stock].astype("Int64")


        mask = ((resultado['familia_ventas'].isin([
        'BEBIDAS CALIENTES',
        ])) | (resultado['nombre'].isin([
            'CHEESECAKE MINI BITES POR 12 UNIDADES .',
            'CHEESECAKE MINI BITES POR 4 UNIDADES .',
            'CHEESECAKE MINI BITES POR 8 UNIDADES .',
            'CHEESECAKE MINI BITES POR 16 UNIDADES .',
            'GRUPO BEBIDAS FRIAS VASO LECHE .',
            'GRUPO BEBIDAS FRIAS SODA DE FRUTA FRUTOS ROJOS',
            'GRUPO BEBIDAS FRIAS SODA DE FRUTA MARACUYA',
            'GRUPO BEBIDAS FRIAS SODA DE FRUTA LULO'])) | (resultado['familia_stock'].isin([
        'BEBIDAS CALIENTES',
        ])))

        ### sumar aritos
        aritos = resultado.loc[resultado[['familia_ventas', 'familia_stock']].eq('ARITOS').any(axis=1), 'nombre'].to_list()
        aritos.remove('ARITOS ARITO CHOCOFLAN .')

        mask_aritos = resultado['nombre'].isin(aritos)
        suma = resultado.loc[mask_aritos, columnas].sum(numeric_only=True)
        mask_destino = resultado['nombre'].eq('ARITOS ARITO .')
        resultado.loc[mask_destino, suma.index] = suma.values
        ################

        resultado.loc[mask, sucursales_stock] = pd.NA
        resultado['valor'] = pd.to_numeric(resultado['valor'], errors='coerce').round().astype('Int64')
        resultado[columnas].to_csv('resultado/resultado.csv', sep='|', index=False)

        #print(resultado.loc[resultado['familia_ventas']=='BEBIDAS CALIENTES', ['nombre','familia_ventas']])
        #print(resultado.loc[resultado['nombre']=='BEBIDAS CALIENTES TE MATCHA .', ['nombre','familia_ventas']])
        #print(resultado.loc[resultado['familia_ventas'].isna(), 'nombre'].tolist())
        #print(resultado.loc[resultado['nombre'] == 'BEBIDAS CALIENTES AMERICANO DOBLE .'].T)
       
        #display(resultado[resultado['familia_ventas'] == 'BEBIDAS CALIENTES'][columnas])
        #display(resultado[resultado['nombre'] == 'MINI BITES POR 12 UNIDADES .'][columnas])
        #display(resultado[columnas])
        #display(ventas[ventas['producto'].str.contains('TARTALETA', na=False)])
        #display(stock[stock['familia'].str.contains('BEBIDAS CALIENTES', na=False)])

        print("\nArchivo resultado.csv generado correctamente. 👍")
        
        
    except Exception as e:
        print(f"Error: {e} 🤮")

@app.command()
def auto():
    """
    3 ==> Copia los valores de ventas/stock al formato para el informe en base_0.xlsx
    """

    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

    ARCHIVO_EXCEL = "base/base_0.xlsx"
    HOJA = "base_0"
    FILE_CSV = "resultado/resultado.csv"

    resultado = pd.read_csv(FILE_CSV, sep='|')
    #print(resultado.columns)
    wb = load_workbook(ARCHIVO_EXCEL)
    original = wb[HOJA]
    hoja_copia = wb.copy_worksheet(original)
    hoja_copia.title = "modificado"

    ws = hoja_copia


    
    with open("json/gemini-code.json", "r", encoding="utf-8") as archivo:
        productos_json = json.load(archivo)

    
    #lista_nombres_json = [x for x in productos_json.keys()] 

  

    ## cambiar los nombres de la columna nombre en resultados.csv por los nombres reales del stock/ventas
    for _, result in resultado.iterrows():
        for nombre, nombre_merge in productos_json.items():
            #print(nombre_merge)
            if result['nombre'] == nombre_merge:
                resultado.loc[result.name, "nombre"] = nombre

    ####___________________________________________________________


    columnas_excel = {
        "salitre": {"venta": 3, "stock": 4},
        "andino": {"venta": 5, "stock": 6},
        "titan": {"venta": 7, "stock": 8},
        "colina": {"venta": 9, "stock": 10},
        "santafe": {"venta": 11, "stock": 12},
        "chia": {"venta": 13, "stock": 14},
        "calle 79": {"venta": 15, "stock": 16},
        "calle 109": {"venta": 17, "stock": 18},
        "calle 122": {"venta": 19, "stock": 20},
        "cedritos": {"venta": 21, "stock": 22},
        "fabrica": 23,
        "valor": 24
        }
    
    ########### funcion principal moverla data de resultados al informe excel
    try:
        print('Generando :::___')
        for fila in range(3, ws.max_row + 1):
            nombre_excel = ws.cell(fila, 2).value
            nombre_excel = str(nombre_excel).strip()
            #print(nombre_excel)
            for _, result in resultado.iterrows():

                if nombre_excel == result['nombre']:
                    #print(fila , nombre_excel, '>', 'salitre', ':', result['salitre'], 'salitre_stock', ':', result['salitre_stock'])
                    ws.cell(row=fila, column=columnas_excel['salitre']['venta'], value=result['salitre'])
                    ws.cell(row=fila, column=columnas_excel['salitre']['stock'], value=result['salitre_stock'])

                    ws.cell(row=fila, column=columnas_excel['andino']['venta'], value=result['andino'])
                    ws.cell(row=fila, column=columnas_excel['andino']['stock'], value=result['andino_stock'])

                    ws.cell(row=fila, column=columnas_excel['titan']['venta'], value=result['titan'])
                    ws.cell(row=fila, column=columnas_excel['titan']['stock'], value=result['titan_stock'])

                    ws.cell(row=fila, column=columnas_excel['colina']['venta'], value=result['colina'])
                    ws.cell(row=fila, column=columnas_excel['colina']['stock'], value=result['colina_stock'])

                    ws.cell(row=fila, column=columnas_excel['santafe']['venta'], value=result['santafe'])
                    ws.cell(row=fila, column=columnas_excel['santafe']['stock'], value=result['santafe_stock'])

                    ws.cell(row=fila, column=columnas_excel['chia']['venta'], value=result['chia'])
                    ws.cell(row=fila, column=columnas_excel['chia']['stock'], value=result['chia_stock'])

                    ws.cell(row=fila, column=columnas_excel['calle 79']['venta'], value=result['calle 79'])
                    ws.cell(row=fila, column=columnas_excel['calle 79']['stock'], value=result['calle 79_stock'])

                    ws.cell(row=fila, column=columnas_excel['calle 109']['venta'], value=result['calle 109'])
                    ws.cell(row=fila, column=columnas_excel['calle 109']['stock'], value=result['calle 109_stock'])

                    ws.cell(row=fila, column=columnas_excel['calle 122']['venta'], value=result['calle 122'])
                    ws.cell(row=fila, column=columnas_excel['calle 122']['stock'], value=result['calle 122_stock'])

                    ws.cell(row=fila, column=columnas_excel['cedritos']['venta'], value=result['cedritos'])
                    ws.cell(row=fila, column=columnas_excel['cedritos']['stock'], value=result['cedritos_stock'])

                    ws.cell(row=fila, column=columnas_excel['fabrica'], value=result['fabrica'])
                    ws.cell(row=fila, column=columnas_excel['valor'], value=result['valor'])
        ##___________________________________________________
        from datetime import datetime
        ahora = datetime.now()
        file = f"base/informes/base_0_{ahora.strftime("%Y-%m-%d-%H-%M-%S")}_modificado.xlsx"
        wb.save(file)
        
        print('\n ARCHIVO BASE GUARDADO ==>', file)
    except Exception as e:
        print(e)

    ####### mostrar faltantes
    encabezados = ['AMERICAN CUPS', 'None', 'VENTAS DIARIAS POR PRODUCTO DEL 18,19,20 DE SEPTIEMBRE DEL 2026', 'TORTAS', 'PRODUCTOS DE SAL', 'GALLETERIA', 'BEBIDAS FRIAS', 'VENTAS DE SEPTIEMBRE 18,19,20 DEL 2026', 'P BROWNIES', 'PRODUCTO', 'MED 10PX', 'TOTAL CAFÉ POR ALMACEN', 'PROMOCION']

    lista_nombres_resultado = []
    lista_nombres_excel = []
    for _ , result in resultado.iterrows():
        lista_nombres_resultado.append(result['nombre'])

    for fila in range(3, ws.max_row + 1):
        nombre_excel = ws.cell(fila, 2).value
        nombre_excel = str(nombre_excel).strip()
        if nombre_excel in encabezados:
            continue
        lista_nombres_excel.append(nombre_excel)

    excel_sin_datos = [n for n in lista_nombres_excel if n not in lista_nombres_resultado]
    sobrantes = [n for n in lista_nombres_resultado if n not in lista_nombres_excel]
    con_datos = len(lista_nombres_excel) - len(excel_sin_datos)

    print(f"\nFilas del informe: {len(lista_nombres_excel)}")
    print(f"  ✓ Con datos:      {con_datos}")
    print(f"  ⚠ Sin datos:       {len(excel_sin_datos)}  (producto nuevo o sin ventas este período)")
    for nombre in excel_sin_datos:
        print(f"      - {nombre}")
    print(f"  ⚠ Sobrantes en resultado.csv: {len(sobrantes)}  (existen en ventas/stock pero no en el Excel)")
    for nombre in sobrantes:
        print(f"      - {nombre}")
            

if __name__ == "__main__":
    app()