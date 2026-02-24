Skip to:

1. [Top Bar](https://colppy.atlassian.net/wiki/spaces/CA/pages/9896058/Provision+Proveedor#_R4abadoa6paq_)
2. [Banner](https://colppy.atlassian.net/wiki/spaces/CA/pages/9896058/Provision+Proveedor#AkBanner)
3. [Sidebar](https://colppy.atlassian.net/wiki/spaces/CA/pages/9896058/Provision+Proveedor#side-navigation)
4. [Main Content](https://colppy.atlassian.net/wiki/spaces/CA/pages/9896058/Provision+Proveedor#AkMainContent)

Atlassian uses cookies to improve your browsing experience, perform analytics and research, and conduct advertising. Accept all cookies to indicate that you agree to our use of cookies on your device. [Atlassian cookies and tracking notice, (opens new window)](https://www.atlassian.com/legal/cookies)

PreferencesOnly necessaryAccept all

Collapse sidebar

Switch sites or apps

[![](https://colppy.atlassian.net/wiki/download/attachments/524289/atl.site.logo?version=5&modificationDate=1733246707398&cacheVersion=1&api=v2)\\
\\
![](https://colppy.atlassian.net/wiki/download/attachments/524289/atl.site.logo?version=5&modificationDate=1733246707398&cacheVersion=1&api=v2)](https://colppy.atlassian.net/wiki)

Colppy Wiki

Search

Create

Create

Help

Log in

Spaces

Apps

* * *

[Colppy API](https://colppy.atlassian.net/wiki/spaces/CA/overview?homepageId=9371654)

![](https://colppy.atlassian.net/wiki/download/attachments/9371652/CA?version=2&modificationDate=1502122488793&cacheVersion=1&api=v2)

More actions

Back to top

Content

Results will update as you type.

- [Introducción](https://colppy.atlassian.net/wiki/spaces/CA/pages/9895962/Introducci+n)

- [Listado de Provisiones y Operaciones Disponibles](https://colppy.atlassian.net/wiki/spaces/CA/pages/16318473/Listado+de+Provisiones+y+Operaciones+Disponibles)









  - [Sesiones](https://colppy.atlassian.net/wiki/spaces/CA/pages/9895964/Sesiones)

  - [Provision Cliente](https://colppy.atlassian.net/wiki/spaces/CA/pages/9895973/Provision+Cliente)

  - [Provisión Contabilidad](https://colppy.atlassian.net/wiki/spaces/CA/pages/19234822/Provisi+n+Contabilidad)

  - [Provisión Empresa](https://colppy.atlassian.net/wiki/spaces/CA/pages/9896007/Provisi+n+Empresa)

  - [Provisión FacturaCompra](https://colppy.atlassian.net/wiki/spaces/CA/pages/9896005/Provisi+n+FacturaCompra)

  - [Provision Inventario - Remitos](https://colppy.atlassian.net/wiki/spaces/CA/pages/11829254/Provision+Inventario+-+Remitos)

  - [Provisión FacturaVenta](https://colppy.atlassian.net/wiki/spaces/CA/pages/9896030/Provisi+n+FacturaVenta)

  - [Operacion alta\_cobro](https://colppy.atlassian.net/wiki/spaces/CA/pages/17760332/Operacion+alta_cobro)

  - [Provisión Pago](https://colppy.atlassian.net/wiki/spaces/CA/pages/68681731/Provisi+n+Pago)

  - [Provision Proveedor](https://colppy.atlassian.net/wiki/spaces/CA/pages/9896058/Provision+Proveedor)









    - [Operación alta\_proveedor](https://colppy.atlassian.net/wiki/spaces/CA/pages/9896063/Operaci+n+alta_proveedor)

    - [Operación editar\_proveedor](https://colppy.atlassian.net/wiki/spaces/CA/pages/9896065/Operaci+n+editar_proveedor)

    - [Operación leer\_proveedor](https://colppy.atlassian.net/wiki/spaces/CA/pages/9896060/Operaci+n+leer_proveedor)

    - [Operación listar\_proveedor](https://colppy.atlassian.net/wiki/spaces/CA/pages/9896067/Operaci+n+listar_proveedor)
  - [Provision Tesorería](https://colppy.atlassian.net/wiki/spaces/CA/pages/9896069/Provision+Tesorer+a)

  - [Parámetros Especiales](https://colppy.atlassian.net/wiki/spaces/CA/pages/128221185/Par+metros+Especiales)

  - [Provisión Lista de Precios](https://colppy.atlassian.net/wiki/spaces/CA/pages/1091633163/Provisi+n+Lista+de+Precios)

  - [Provisión Integraciones](https://colppy.atlassian.net/wiki/spaces/CA/pages/2465660946/Provisi+n+Integraciones)

  - [Provisión monedas](https://colppy.atlassian.net/wiki/spaces/CA/pages/4644405249/Provisi+n+monedas)
- [APÉNDICE](https://colppy.atlassian.net/wiki/spaces/CA/pages/9896077/AP+NDICE)

- [Ayuda](https://colppy.atlassian.net/wiki/spaces/CA/pages/3165028353/Ayuda)


Space apps

[draw.io Diagrams](https://colppy.atlassian.net/wiki/display/CA/customcontent/list/ac%3Acom.mxgraph.confluence.plugins.diagramly%3Adrawio-diagram)

![](https://ac.draw.io/images/drawlogo48.png)

* * *

You‘re viewing this with anonymous access, so some content might be blocked.

Close

Side Navigation Drag Handle

Colppy API

/

Provision Proveedor

[Published Jan 24, 2014](https://colppy.atlassian.net/wiki/spaces/CA/history/9896058)

- ![](<Base64-Image-Removed>)Anonymous Flamingo


More actions

# Provision Proveedor

![](https://colppy.atlassian.net/wiki/aa-avatar/557058:79dffa75-6956-4e0b-9fb3-953ae91566cb)

By Mariano Rizzi (Unlicensed)

Jan 24, 2014

1 min

Add a reaction

[Cloud editor](https://colppy.atlassian.net/wiki/spaces/CA/pages/9896058/www.atlassian.com)

Operaciones alta\_proveedor, editar\_proveedor, leer\_proveedor y lista\_proveedor

Todos los campos mencionados a continuación son enviados al servidor de API en las operaciones de alta\_proveedor y editar\_proveedor, con el formato de propiedades de un objeto JSON como se muestra en los ejemplos respectivos.

Todos los campos son requeridos y deberán contener nulo ('') en caso de no tener valor.

En la tabla que se muestra a continuación se listan los campos requeridos, su tipo, su valores permitidos y si deben obligatoriamente contener un valor que no sea nulo ('').

|     |     |
| --- | --- |
| **Nombre del campo** | **Requerimientos** |
| idEmpresa | Identificador de la.Empresa en todo el sistema. Numérico entero. Obligatorio |
| idProveedor | Identificador del Proveedor de la Empresa. Numérico entero. Obligatorio. |
| NombreFantasia | Alfanumérico.No más largo de 60 caracteres. Obligatorio |
| RazonSocial | Alfanumérico.No más largo de 60 caracteres. Obligatorio |
| CUIT | Formato de cuit valido (XX-XXXXXXXX-X). Se valida con fórmula de dígito verificador. Además se valida si existe un cliente con el mismo CUIT |
| DirPostal | Dirección Postal del Proveedor.No más largo de 60 caracteres |
| DirPostalCiudad | Ciudad.No más largo de 40 caracteres |
| DirPostalCodigoPostal | Código Postal. No más largo de 10 caracteres |
| DirPostalProvincia | Provincia. No más largo de 40 caracteres. Debe ser un dato de una lista de posibles provincias1 |
| DirPostalPais | País.No más largo de 15 caracteres |
| Telefono | No más largo de 18 caracteres |
| Email | No más largo de 100 caracteres |
| Activo | Valores posibles 0=Inactivo o 1=Ativo. Obligatorio |
| FechaAlta | Formato 'dd-mm-aaaa' o 'dd-mm-aa' |
| DirFiscal | Dirección Fiscal del Proveedor.No más largo de 60 caracteres |
| DirFiscalCiudad | No más largo de 40 caracteres |
| DirFiscalCodigoPostal | No más largo de 10 caracteres |
| DirFiscalProvincia | No más largo de 40 caracteres. Debe ser un dato de una lista de posibles provincias1 |
| DirFiscalPais | No más largo de 15 caracteres |
| Banco | Alfanumérico.Nombre del Banco del Cliente para transferencias. |
| CBU | Formato '9999999-9-9999999999999-9' |
| Producto | Alfanumérico. Descripción de productos o servicios que vende.No más largo de 100 caracteres |
| idCondiciónPago | Valores de acuerdo a tabla del Apéndice. |
| idCondiciónIva | Valores de acuerdo a tabla del Apéndice. |
| porcentajeIVA | Debe ser un dato de una lista de posibles IVA(21,10.5,27) |
| idTipoPercepcion | Valores de acuerdo a tabla de Apéndice. |
| idRetGanancias | Valores de acuerdo a tabla de Apéndice. |
| idPlanCuenta | Alfanumérico.Número de Cuenta del Plan de Cuentas correspondiente a la cuenta de egresos por defecto en la facturas de compra de este proveedor |

Collapse action bar

Open Comments Panel

Open Details Panel

Rovo Button

Add a comment

Add a reaction

{"serverDuration": 46, "requestCorrelationId": "b28cbfd57a7f49889bdf21c9f510909e"}