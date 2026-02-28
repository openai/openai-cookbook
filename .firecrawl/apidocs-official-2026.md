- Body
- Headers (11)

- Body
- Headers (0)

- Body
- Headers (0)

- Body
- Headers (0)

- Body
- Headers (0)

- Body
- Headers (0)

- Body
- Headers (0)

- Body
- Headers (0)

- Body
- Headers (0)

- Body
- Headers (0)

- Body
- Headers (0)

- Body
- Headers (11)

- Body
- Headers (0)

- Body
- Headers (0)

- Body
- Headers (0)

- Body
- Headers (0)

- Body
- Headers (0)

- Body
- Headers (0)

- Body
- Headers (0)

- Body
- Headers (11)

- Body
- Headers (0)

- Body
- Headers (0)

- Body
- Headers (0)

- Body
- Headers (0)

- Body
- Headers (0)

- Body
- Headers (0)

Public

Documentation Settings

ENVIRONMENT

sandbox

LAYOUT

Double Column

LANGUAGE

cURL - cURL

Colppy API

[Introduction](https://apidocs.colppy.com/#intro)

Sesiones

Clientes

Contabilidad

Empresa

POST

https://login.colppy.com/resources/php/paneldecontrol/TC\_graficoResultados.php

# Colppy API

**Colppy** esta construido en base a una API propia. Esta API es el nexo entre el sitio web de Colppy y sus servidores. Como desarrolladores podemos usar este nexo para crear nuestras propias aplicaciones contables o automatizar nuestros sistemas de gestión aprovechando el potencial contable que ofrece Colppy.

Para empezar a trabajar con **Colppy API** primero debemos ingresar a la web de desarrollador de Colppy, registrar un usuario y contraseña.

Luego, ingresar a la documentación de las provisiones y operaciones disponibles de Colppy API.

Recuerda que para poder utilizar el ambiente de prueba Staging una vez creado el usuario DEV tarda 24 horas en habilitarse.

**Qué es Colppy API?**

La API de Colppy utiliza el protocolo HTTPS para hacer las pegadas a la API. Colppy API permite mediante una solicitud en formato json; iniciar sesión, realizar altas y bajas de facturas, leer datos de empresas o cliente entre otras funcionalidades.

**Cómo empiezo?**

El primer paso para empezar a desarrollar es registrar usuario y contraseña en la Web de desarrolladores de Colppy. Para realizar una petición podemos o generar un script en php que utilice Curl o utilizando alguna herramienta que puedan ejecutar HTTP POST Request (Por ej. httprequester para Firefox o PostMan para Chrome).

**Cómo realizo una petición?**

La url de Colppy API para realizar pruebas es [https://staging.colppy.com/lib/frontera2/service.php](https://staging.colppy.com/lib/frontera2/service.php). El punto de acceso a Colppy API en su versión Producción es [https://login.colppy.com/lib/frontera2/service.php](https://login.colppy.com/lib/frontera2/service.php). Para poder generar una petición debemos ejecutar HTTP POST Request a una de las URLs en donde se encuentra el servicios, ya sea de producción o testing con JSON que tiene el siguiente formato:
El JSON se divide en tres partes **auth, service y parameters**.

`{    "auth":{       "usuario":"usuario_API",       "password":"Clave MD5"    },    "service":{       "provision":"Usuario",       "operacion":"iniciar_sesion"    },    "parameters":{       "usuario":"Usuario_Colppy",       "password":"Clave MD5"    } }`

En **auth** van tus credenciales, con las que te registraste en la web de desarrolladores de Colppy, y el MD5 de la contraseña que utilizaste para registraste. Por ejemplo si mi nombre usuario como desarrollador es SujetoDePrueba y mi contraseña **SujetoDePruebaContraseña**, el JSON quedaría de la siguiente forma:

`{       "auth": {             "usuario": "SujetoDePrueba",             "password": "d0edfe89f30a78ef45ab9a22bd0f826b"       } }`

El md5 de la cadena **"SujetoDePruebaContraseña"** es la cadena **"d0edfe89f30a78ef45ab9a22bd0f826b"**.
En **service** se especifica que es lo que deseo hacer con en la petición. Cada alta, baja y modificación de colppy están en diferentes Provisiones y cada una de estas en diferentes operaciones. La Provisiones hacen referencia sobre cual de los módulo Colppy deseo trabajar, y la operación hace referencia a lo que deseo hacer con ese módulo. Existe un Índice con las distintas Provisiones y Operaciones que soporta Colppy. Por ejemplo si lo que quiero hacer es iniciar sesión en Colppy lo que tengo que hacer es modificar el campo _provision_ con el nombre del modulo al que quiero acceder en este caso _Usuario_, luego me fijo en el índice de provisiones y operaciones de Colppy y verifico que exista la operaciones iniciar\_sesion, Entonces en el campo operaciones lo cambio a iniciar\_sesion. Entonces el JSON quedaría de la siguiente manera

`{    "service": {             "provision": "Usuario",             "operacion": "iniciar_sesion"       }, }`

Nota importante sobre el nombre de las provisiones y operaciones; son sensible a mayúsculas. Siempre tener el índice de provisiones y operaciones a mano. En parameters van los parametros que espera la operacion para poderse ejecutar. Estos parámetros varían de provisión en provision y de operación en operacion. En este caso estamos tratando de iniciar sesion en Colppy, si nos fijamos en el índice de provisiones y operaciones en la sección de la provisión sesion, podemos ver los parámetros que espera la operación en el JSON.

En el nuestro ejemplo el JSON final quedaría de la siguiente manera:

`{    "auth":{       "usuario":"Usuario Desarrollador",       "password":"Password Desarollador"    },    "service":{       "provision":"Usuario",       "operacion":"iniciar_sesion"    },    "parameters":{       "usuario":"UsuarioColppy",       "password":"ContraseñaColppy"    } }`

Una vez que ejecutamos la HTTP POST Request con nuestro JSON, Colppy API nos va a responder con un mensaje informándonos si el requerimiento se realizó con éxito o no.

Ejemplo de una respuesta de éxito:

`{    "service":{       "provision":"Usuario",       "operacion":"iniciar_sesion",       "version":"1_0_0_0",       "response_date":"2014-24-06 17:10:19"    },    "result":{       "estado":0,       "mensaje":"La operaci\u00f3n se realiz\u00f3 correctamente"    },    "response":{       "success":true,       "message":"La operacion se realizo con exito.",       "data":{          "claveSesion":"b5a97564ad59e624a6ba545ecd3ca112"       }    } }`

## Sesiones

Estos son los servicios que debes usar para iniciar y cerrar sesión en Colppy. Es muy importante que recuerdes que previamente debes haberte registrado como desarrollador en [Colppy Developers](http://dev.colppy.com/) y con esas credenciales (email y MD5 de la contraseña) vas a poder usar la API.

También es muy importante recordarte que además de las credenciales de API, siempre vas a necesitar las credenciales (usuario y MD5 de la contraseña) de una empresa registrada en colppy.

### POSTIniciar Sesión

https://staging.colppy.com/lib/frontera2/service.php

Para el inicio de sesión se utiliza la operación **iniciar\_sesión** de la provisión **Usuario**. A este servicio se le pasa el usuario y la contraseña en md5.

Si las credenciales son correctas el servicio te devuelve una **claveSesion**, la cual es requerida para consumir el resto de los servicios.

La duración de las sesiones es de 60 minutos que se renuevan por 60 minutos más cada vez que se utiliza la **claveSesion** en alguna petición.

#### Parámetros

| Campo | Tipo | Requerido | Descripción |
| --- | --- | --- | --- |
| auth.usuario | string | Si | Usuario dado de alta en [Colppy Developers](http://dev.colppy.com/) |
| auth.password | string | Si | Contraseña en MD5 del usuario dado de alta en [Colppy Developers](http://dev.colppy.com/) |
| parameters.service.provision | string | Si | Nombre de la Provisión en este caso **Usuario** |
| parameters.service.operacion | string | Si | Nombre de la Operación en este caso **iniciar\_sesion** |
| parameters.sesion.usuario | string | Si | Usuario de la empresa que vas a integrar |
| parameters.sesion.password | string | Si | Contraseña en MD5 del usuario de la empresa que vas a integrar |

Bodyraw (json)

View More

json

```json
{
    "auth": {
        "usuario": "<API_USERNAME>",
        "password": "<API_PASSWORD_MD5>"
    },
    "service": {
        "provision": "Usuario",
        "operacion": "iniciar_sesion"
    },
    "parameters": {
        "usuario": "<COLPPY_USERNAME>",
        "password": "<COLPPY_PASSWORD_MD5>"
    }
}
```

Example Request

Iniciar Sesión: Con una contraseña de usuario API incorrecta

View More

curl

```curl
curl --location 'https://staging.colppy.com/lib/frontera2/service.php' \
--data-raw '{
    "auth": {
        "usuario": "username@dominio.com",
        "password": "e7ac6f61043c5a26011204b33bff69ec"
    },
    "service": {
        "provision": "Usuario",
        "operacion": "iniciar_sesion"
    },
    "parameters": {
        "usuario": "username.company@dominio.com",
        "password": "83ede967c0121e2e3d547bf15864231e"
    }
}'
```

200 OK

Example Response

- Body
- Headers (11)

View More

json

```json
{
  "service": {
    "provision": "Usuario",
    "operacion": "iniciar_sesion",
    "response_date": "2020-06-30 21:21:44"
  },
  "result": {
    "estado": 602,
    "mensaje": "La contraseña de usuario es incorrecta"
  },
  "response": null
}
```

Server

nginx

Date

Wed, 01 Jul 2020 00:05:06 GMT

Content-Type

application/json; charset=utf-8

Transfer-Encoding

chunked

Connection

keep-alive

Access-Control-Allow-Origin

\*

Access-Control-Allow-Methods

GET,PUT,POST,DELETE,HEAD,OPTIONS

Access-Control-Allow-Headers

Content-Type, Authorization, X-Authorization,X-Requested-With

Allow

GET,HEAD,POST,OPTIONS,TRACE

X-XSS-Protection

1; mode=block

X-Content-Type-Options

nosniff

### POSTCerrar Sesión

https://staging.colppy.com/lib/frontera2/service.php

Para cerrar sesión se utiliza la operación **cerrar\_sesión** de la provisión **Usuario**. Este servicio sólo recibe el par usuario y claveSesion.

Si la sesión es válida, entonces lo que hace es invalidarla.

#### Parámetros

| Campo | Tipo | Requerido | Descripción |
| --- | --- | --- | --- |
| auth.usuario | string | Si | Usuario dado de alta en [Colppy Developers](http://dev.colppy.com/) |
| auth.password | string | Si | Contraseña en MD5 del usuario dado de alta en [Colppy Developers](http://dev.colppy.com/) |
| parameters.service.provision | string | Si | Nombre de la Provisión en este caso **Usuario** |
| parameters.service.operacion | string | Si | Nombre de la Operación en este caso **cerrar\_sesión** |
| parameters.sesion.usuario | string | Si | Usuario de la empresa que vas a integrar |
| parameters.sesion.claveSesion | string | Si | Clave de sesión obtenida en el inicio de sesión |

Bodyraw (json)

View More

json

```json
{
    "auth": {
        "usuario": "<API_USERNAME>",
        "password": "<API_PASSWORD_MD5>"
    },
    "service": {
        "provision": "Usuario",
        "operacion": "cerrar_sesion"
    },
    "parameters": {
        "sesion": {
            "usuario": "<COLPPY_USERNAME>",
            "claveSesion": ""
        }
    }
}
```

Example Request

Cerrar Sesión: Con credenciales de empresa incorrectas

View More

curl

```curl
curl --location 'https://staging.colppy.com/lib/frontera2/service.php' \
--data-raw '{
    "auth": {
        "usuario": "username@dominio.com",
        "password": "e7ac6f61043c5a26011204b33bff69ec"
    },
    "service": {
        "provision": "Usuario",
        "operacion": "cerrar_sesion"
    },
    "parameters": {
        "sesion": {
            "usuario": "username.company@dominio.com",
            "claveSesion": "f2b15f2********************c6bc7"
        }
    }
}'
```

Example Response

- Body
- Headers (0)

View More

json

```json
{
  "service": {
    "provision": "Usuario",
    "operacion": "cerrar_sesion",
    "version": "1_0_0_0",
    "response_date": "2020-06-30 21:48:47"
  },
  "result": {
    "estado": 1,
    "mensaje": "La sesion no es válida."
  },
  "response": null
}
```

No response headers

This request doesn't return any response headers

## Clientes

Todos los campos mencionados a continuación son enviados al servidor de API en las operaciones de alta\_cliente y editar\_cliente, con el formato de propiedades de un objeto JSON como se muestra en los ejemplos respectivos.
Todos los campos son requeridos y deberán contener nulo ('') en caso de no tener valor.
En la tabla que se muestra a continuación se listan los campos requeridos, su tipo, su valores permitidos y si deben obligatoriamente contener un valor que no sea nulo ('').

View More

| Nombre del campo **info\_general** | Requerimientos |
| --- | --- |
| CUIT | Formato de CUIT válido (XX-XXXXXXXX-X). Se valida con fórmula de dígito verificador. Además se valida si existe un cliente con el mismo CUIT (Obligatorio, pero puede venir con valor vacio "") |
| DirPostalCiudad | Ciudad. No más largo de 40 caracteres |
| DirPostalCodigoPostal | Código Postal. No más largo de 10 caracteres |
| DirPostalPais | País. No más largo de 15 caracteres |
| DirPostalProvincia | Provincia. No más largo de 40 caracteres. Debe ser un dato de una lista de posibles provincias1 |
| DNI | Numérico - 10 caracteres |
| Email | No más largo de 100 caracteres |
| idCliente | Identificador del Cliente de la Empresa. Numérico entero. Obligatorio para edición y lectura |
| idEmpresa | Identificador de la.Empresa en todo el sistema. Numérico entero. Obligatorio |
| NombreFantasia | Alfanumérico. No más largo de 60 caracteres. Obligatorio |
| RazonSocial | Alfanumérico. No más largo de 60 caracteres. Obligatorio |
| Telefono | No más largo de 18 caracteres |

View More

| Nombre del campo **info\_otra** | Requerimientos |
| --- | --- |
| Activo | Valores posibles 0=Inactivo o 1=Activo. Obligatorio |
| FechaAlta | Formato 'dd-mm-aaaa' o 'dd-mm-aa' |
| DirFiscal | Dirección Fiscal del Cliente. No más largo de 60 caracteres |
| DirFiscalCiudad | No más largo de 40 caracteres |
| DirFiscalCodigoPostal | No más largo de 10 caracteres |
| DirFiscalProvincia | No más largo de 40 caracteres. Debe ser un dato de una lista de posibles provincias1 |
| DirFiscalPais | No más largo de 15 caracteres |
| idCondiciónPago | Valores de acuerdo a tabla del Apéndice. |
| idCondiciónIva | Valores de acuerdo a tabla del Apéndice. |
| porcentajeIVA | Debe ser un dato de una lista de posibles IVA(21,10.5,27) |
| idPlanCuenta | Alfanumérico. Número de Cuenta del Plan de Cuentas correspondiente a la cuenta de ingresos por defecto en la facturas de venta de este cliente (Obligatorio, pero puede venir con valor vacio "") |
| CuentaCredito | Alfanumérico. Cuenta de Deudores por Ventas. |

### POSTAlta Cliente

https://staging.colppy.com/lib/frontera2/service.php

## Comprobaciones:

- La sesión es válida (si están activadas las sesiones). Implica que el usuario exista.
- La empresa existe y pertenece al usuario. (Se hace explícitamente al indicar los datos en la petición)

## Errores posibles

- ID de empresa faltante.
- Razón Social faltante.
- Nombre Fantasía faltante.
- Error al realizar el alta.
- El CUIT ya existe; está siendo usado para otro cliente.

Bodyraw (json)

View More

json

```json
{
    "auth": {
        "usuario": "<API_USERNAME>",
        "password": "<API_PASSWORD_MD5>"
    },
    "service": {
        "provision": "Cliente",
        "operacion": "alta_cliente"
    },
    "parameters": {
        "sesion": {
            "usuario": "<COLPPY_USERNAME>",
            "claveSesion": ""
        },
        "info_general": {
            "idUsuario": "a",
            "idCliente": "",
            "idEmpresa": "11675",
            "NombreFantasia": "ACME",
            "RazonSocial": "ACME S.A.",
            "CUIT": "20-08442162-7",
            "dni": "",
            "DirPostal": "San Martin 1234.",
            "DirPostalCiudad": "CABA",
            "DirPostalCodigoPostal": "1234",
            "DirPostalProvincia": "CABA",
            "DirPostalPais": "Argentina",
            "Telefono": "43211234",
            "Email": "aaaaaa@aaa.com"
        },
        "info_otra": {
            "Activo": "1",
            "FechaAlta": "",
            "DirFiscal": "",
            "DirFiscalCiudad": "",
            "DirFiscalCodigoPostal": "",
            "DirFiscalProvincia": "",
            "DirFiscalPais": "",
            "idCondicionPago": "",
            "idCondicionIva": "",
            "porcentajeIVA": "",
            "idPlanCuenta": "",
            "CuentaCredito": "",
            "DirEnvio": "",
            "DirEnvioCiudad": "",
            "DirEnvioCodigoPostal": "",
            "DirEnvioProvincia": "",
            "DirEnvioPais": ""
        }
    }
}
```

Example Request

Alta Cliente

View More

curl

```curl
curl --location 'https://staging.colppy.com/lib/frontera2/service.php' \
--data-raw '{
    "auth": {
        "usuario": "<API_USERNAME>",
        "password": "<API_PASSWORD_MD5>"
    },
    "service": {
        "provision": "Cliente",
        "operacion": "alta_cliente"
    },
    "parameters": {
        "sesion": {
            "usuario": "<COLPPY_USERNAME>",
            "claveSesion": ""
        },
        "info_general": {
            "idUsuario": "a",
            "idCliente": "",
            "idEmpresa": "11675",
            "NombreFantasia": "ACME",
            "RazonSocial": "ACME S.A.",
            "CUIT": "20-08442162-7",
            "dni": "",
            "DirPostal": "San Martin 1234.",
            "DirPostalCiudad": "CABA",
            "DirPostalCodigoPostal": "1234",
            "DirPostalProvincia": "CABA",
            "DirPostalPais": "Argentina",
            "Telefono": "43211234",
            "Email": "aaaaaa@aaa.com"
        },
        "info_otra": {
            "Activo": "1",
            "FechaAlta": "",
            "DirFiscal": "",
            "DirFiscalCiudad": "",
            "DirFiscalCodigoPostal": "",
            "DirFiscalProvincia": "",
            "DirFiscalPais": "",
            "idCondicionPago": "",
            "idCondicionIva": "",
            "porcentajeIVA": "",
            "idPlanCuenta": "",
            "CuentaCredito": "",
            "DirEnvio": "",
            "DirEnvioCiudad": "",
            "DirEnvioCodigoPostal": "",
            "DirEnvioProvincia": "",
            "DirEnvioPais": ""
        }
    }
}'
```

Example Response

- Body
- Headers (0)

No response body

This request doesn't return any response body

No response headers

This request doesn't return any response headers

### POSTLeer fondo pago

https://staging.colppy.com/lib/frontera2/service.php

Esta petición puede traer tanto items ya guardados de cobro como también entre 3 y 5 items con campos vacíos todo dependiendo de las condiciones de parámetros que se pasen. Si el campo add ==1 y existe el idCobro entonces se devuelve 3 filas de elementos con campos vacíos. Si el Add es !=1 y el idCobro no es vacío entonces debe devolver null en el caso de que no se encuentre nada o las filas que correspondan con sus campos. Si el idCobro es vació entonces devuelve solo 5 filas con campos vacíos.

### Parametros:

- add: Identificador Numérico entero. Puede ser vacio o 1.
- idEmpresa: Identificador de la.Empresa en todo el sistema. Numérico entero. Obligatorio
- idCobro: Identificador del cobro. Numérico entero. Puede ser vacio.

Bodyraw (json)

View More

json

```json
{
    "auth": {
        "usuario": "<API_USERNAME>",
        "password": "<API_PASSWORD_MD5>"
    },
    "service": {
        "provision": "Cliente",
        "operacion": "AR_leer_fondos_pagos"
    },
    "parameters": {
        "sesion": {
            "usuario": "<COLPPY_USERNAME>",
            "claveSesion": ""
        },
        "add": 0,
        "idEmpresa": 24928,
        "idCobro": "1238275"
    }
}
```

Example Request

Leer fondo pago

View More

curl

```curl
curl --location 'https://staging.colppy.com/lib/frontera2/service.php' \
--data '{
    "auth": {
        "usuario": "<API_USERNAME>",
        "password": "<API_PASSWORD_MD5>"
    },
    "service": {
        "provision": "Cliente",
        "operacion": "AR_leer_fondos_pagos"
    },
    "parameters": {
        "sesion": {
            "usuario": "<COLPPY_USERNAME>",
            "claveSesion": ""
        },
        "add": 0,
        "idEmpresa": 24928,
        "idCobro": "1238275"
    }
}'
```

Example Response

- Body
- Headers (0)

No response body

This request doesn't return any response body

No response headers

This request doesn't return any response headers

### POSTAlta de Cobro

https://staging.colppy.com/lib/frontera2/service.php

Esta petición puede traer tanto items ya guardados de cobro como también entre 3 y 5 items con campos vacíos todo dependiendo de las condiciones de parámetros que se pasen. Si el campo add ==1 y existe el idCobro entonces se devuelve 3 filas de elementos con campos vacíos. Si el Add es !=1 y el idCobro no es vacío entonces debe devolver null en el caso de que no se encuentre nada o las filas que correspondan con sus campos. Si el idCobro es vació entonces devuelve solo 5 filas con campos vacíos.

### Parametros:

- add: Identificador Numérico entero. Puede ser vacio o 1.
- idEmpresa: Identificador de la.Empresa en todo el sistema. Numérico entero. Obligatorio
- idCobro: Identificador del cobro. Numérico entero. Puede ser vacio.

Bodyraw (json)

View More

json

```json
{
    "auth": {
        "usuario": "<API_USERNAME>",
        "password": "<API_PASSWORD_MD5>"
    },
    "service": {
        "provision": "Cliente",
        "operacion": "alta_cobro"
    },
    "parameters": {
        "sesion": {
            "usuario": "<COLPPY_USERNAME>",
            "claveSesion": ""
        },

        "cobros": [],
        "mediospagos": [{\
            "idMedioCobro": "Transferencia",\
            "idPlanCuenta": "Santander",\
            "Banco": "",\
            "nroCheque": "",\
            "fechaValidez": "",\
            "importe": 888,\
            "VAD": "S",\
            "Conciliado": "",\
            "idTabla": 0,\
            "idElemento": 0,\
            "idItem": 0\
        }],
        "estesoreria": "0",
        "idUsuario": "dario.rebora@colppy.com",
        "idCobro": "",
        "idCliente": "2946676",
        "idEmpresa": "24928",
        "nroRecibo1": "8888",
        "nroRecibo2": "000090885",
        "fechaCobro": "05-11-2019",
        "idEstadoCobro": "Aprobado",
        "descripcion": "",
        "valorCambio": "0",
        "totalEsteCobro": 0,
        "saldoFacturas": 405,
        "anticipo": 0,
        "descuentos": 0,
        "intereses": 0,
        "retencionIIBB": 0,
        "totalACobrar": 0,
        "idMedioCobro": "Transferencia",
        "totalCobrado": 888,
        "retencionOtras": 0,
        "retsufridas": [],
        "retsufridasotras": [],
        "diferenciaTipoCambio": 0
    }
}
```

Example Request

Alta de Cobro

View More

curl

```curl
curl --location 'https://staging.colppy.com/lib/frontera2/service.php' \
--data-raw '{
    "auth": {
        "usuario": "<API_USERNAME>",
        "password": "<API_PASSWORD_MD5>"
    },
    "service": {
        "provision": "Cliente",
        "operacion": "alta_cobro"
    },
    "parameters": {
        "sesion": {
            "usuario": "<COLPPY_USERNAME>",
            "claveSesion": ""
        },

        "cobros": [],
        "mediospagos": [{\
            "idMedioCobro": "Transferencia",\
            "idPlanCuenta": "Santander",\
            "Banco": "",\
            "nroCheque": "",\
            "fechaValidez": "",\
            "importe": 888,\
            "VAD": "S",\
            "Conciliado": "",\
            "idTabla": 0,\
            "idElemento": 0,\
            "idItem": 0\
        }],
        "estesoreria": "0",
        "idUsuario": "dario.rebora@colppy.com",
        "idCobro": "",
        "idCliente": "2946676",
        "idEmpresa": "24928",
        "nroRecibo1": "8888",
        "nroRecibo2": "000090885",
        "fechaCobro": "05-11-2019",
        "idEstadoCobro": "Aprobado",
        "descripcion": "",
        "valorCambio": "0",
        "totalEsteCobro": 0,
        "saldoFacturas": 405,
        "anticipo": 0,
        "descuentos": 0,
        "intereses": 0,
        "retencionIIBB": 0,
        "totalACobrar": 0,
        "idMedioCobro": "Transferencia",
        "totalCobrado": 888,
        "retencionOtras": 0,
        "retsufridas": [],
        "retsufridasotras": [],
        "diferenciaTipoCambio": 0
    }
}'
```

Example Response

- Body
- Headers (0)

No response body

This request doesn't return any response body

No response headers

This request doesn't return any response headers

### POSTEditar Cliente

https://staging.colppy.com/lib/frontera2/service.php

## Comprobaciones:

- La sesión es válida (si están activadas las sesiones). Implica que el usuario exista.
- La empresa existe y pertenece al usuario.
- El cliente existe y pertenece a la empresa.

## Errores posibles

- Falta el campo idEmpresa, idCliente, idUsuario ó NombreFantasia.
- No se encuentra el cliente.
- El CUIT ya pertenece a otro cliente

Bodyraw (json)

View More

json

```json
{
    "auth": {
        "usuario": "<API_USERNAME>",
        "password": "<API_PASSWORD_MD5>"
    },
    "service": {
        "provision": "Cliente",
        "operacion": "editar_cliente"
    },
    "parameters": {
        "sesion": {
            "usuario": "<COLPPY_USERNAME>",
            "claveSesion": ""
        },
        "info_general": {
            "idUsuario": "a",
            "idCliente": "3765843",
            "idEmpresa": "11675",
            "NombreFantasia": "ACME",
            "RazonSocial": "ACME S.A.",
            "CUIT": "20-08442162-7",
            "DirPostal": "San Martin 1234.",
            "DirPostalCiudad": "CABA",
            "DirPostalCodigoPostal": "1234",
            "DirPostalProvincia": "CABA",
            "DirPostalPais": "Argentina",
            "Telefono": "43211234",
            "Email": "aaaaaa@aaa.com"
        },
        "info_otra": {
            "Activo": "1",
            "FechaAlta": "",
            "DirFiscal": "",
            "DirFiscalCiudad": "",
            "DirFiscalCodigoPostal": "",
            "DirFiscalProvincia": "",
            "DirFiscalPais": "",
            "idCondicionPago": "",
            "idCondicionIva": "",
            "porcentajeIVA": "",
            "idPlanCuenta": "",
            "CuentaCredito": "",
            "DirEnvio": "",
            "DirEnvioCiudad": "",
            "DirEnvioCodigoPostal": "",
            "DirEnvioProvincia": "",
            "DirEnvioPais": ""
        }
    }
}
```

Example Request

Editar Cliente

View More

curl

```curl
curl --location 'https://staging.colppy.com/lib/frontera2/service.php' \
--data-raw '{
    "auth": {
        "usuario": "<API_USERNAME>",
        "password": "<API_PASSWORD_MD5>"
    },
    "service": {
        "provision": "Cliente",
        "operacion": "editar_cliente"
    },
    "parameters": {
        "sesion": {
            "usuario": "<COLPPY_USERNAME>",
            "claveSesion": ""
        },
        "info_general": {
            "idUsuario": "a",
            "idCliente": "3765843",
            "idEmpresa": "11675",
            "NombreFantasia": "ACME",
            "RazonSocial": "ACME S.A.",
            "CUIT": "20-08442162-7",
            "DirPostal": "San Martin 1234.",
            "DirPostalCiudad": "CABA",
            "DirPostalCodigoPostal": "1234",
            "DirPostalProvincia": "CABA",
            "DirPostalPais": "Argentina",
            "Telefono": "43211234",
            "Email": "aaaaaa@aaa.com"
        },
        "info_otra": {
            "Activo": "1",
            "FechaAlta": "",
            "DirFiscal": "",
            "DirFiscalCiudad": "",
            "DirFiscalCodigoPostal": "",
            "DirFiscalProvincia": "",
            "DirFiscalPais": "",
            "idCondicionPago": "",
            "idCondicionIva": "",
            "porcentajeIVA": "",
            "idPlanCuenta": "",
            "CuentaCredito": "",
            "DirEnvio": "",
            "DirEnvioCiudad": "",
            "DirEnvioCodigoPostal": "",
            "DirEnvioProvincia": "",
            "DirEnvioPais": ""
        }
    }
}'
```

Example Response

- Body
- Headers (0)

No response body

This request doesn't return any response body

No response headers

This request doesn't return any response headers

### POSTLeer Cliente

https://staging.colppy.com/lib/frontera2/service.php

## Comprobaciones:

- La sesión es válida (si están activadas las sesiones). Implica que el usuario exista.
- La empresa existe y pertenece al usuario.
- El cliente existe y pertenece a la empresa. (Se hace implícito al buscar por el par \[idCliente, idEmpresa\])

## Errores posibles

- ID de empresa faltante.
- ID de cliente faltante.
- No se encuentra el cliente.

Bodyraw (json)

View More

json

```json
{
    "auth": {
        "usuario": "<API_USERNAME>",
        "password": "<API_PASSWORD_MD5>"
    },
    "service": {
        "provision": "Cliente",
        "operacion": "leer_cliente"
    },
    "parameters": {
        "sesion": {
           "usuario": "<COLPPY_USERNAME>",
            "claveSesion": ""
        },
        "idEmpresa": "11675",
        "idCliente": "3765843"
    }
}
```

Example Request

Leer Cliente exitoso

View More

curl

```curl
curl --location 'https://staging.colppy.com/lib/frontera2/service.php' \
--data '{
    "auth": {
        "usuario": "<API_USERNAME>",
        "password": "<API_PASSWORD_MD5>"
    },
    "service": {
        "provision": "Cliente",
        "operacion": "leer_cliente"
    },
    "parameters": {
        "sesion": {
           "usuario": "<COLPPY_USERNAME>",
            "claveSesion": ""
        },
        "idEmpresa": "11675",
        "idCliente": "3964254"
    }
}'
```

200 OK

Example Response

- Body
- Headers (11)

View More

json

```json
{
  "service": {
    "provision": "Cliente",
    "operacion": "leer_cliente",
    "version": "1_0_0_0",
    "response_date": "2020-10-02 11:21:07"
  },
  "result": {
    "estado": 0,
    "mensaje": "La operación se realizó correctamente"
  },
  "response": {
    "success": true,
    "message": "La operación se realizó con éxito.",
    "data": {
      "idEmpresa": "11675",
      "idCliente": "3964254",
      "RazonSocial": "ABEL NEMECIO GONZALEZ",
      "NombreFantasia": "ABEL NEMECIO GONZALEZ",
      "FechaAlta": "03-08-2020",
      "DirPostal": "GENERAL PAZ 617",
      "DirPostalCiudad": "POSADAS",
      "DirPostalCodigoPostal": "3300",
      "DirPostalProvincia": "Misiones",
      "DirPostalPais": null,
      "DirFiscal": "",
      "DirFiscalCiudad": "",
      "DirFiscalCodigoPostal": "",
      "DirFiscalProvincia": "Misiones",
      "DirFiscalPais": "",
      "Telefono": "",
      "Fax": "",
      "Activo": "1",
      "LimiteCredito": "0.00",
      "idCondicionPago": "0",
      "idCondicionIva": "1",
      "CUIT": "20-12450692-2",
      "Producto": null,
      "idTipoPercepcion": "0",
      "CertificadoExclusion": "",
      "idPlanCuenta": "",
      "NroCuenta": "",
      "CBU": null,
      "Banco": null,
      "DesBanco": null,
      "porcentajeIVA": "0",
      "porcentajeDesc": "0.00",
      "idRetGanancias": null,
      "Email": "@gmail.com",
      "CuentaCredito": null,
      "meliBuyerId": null,
      "DirEnvio": "",
      "DirEnvioCiudad": "",
      "DirEnvioCodigoPostal": "",
      "DirEnvioProvincia": "",
      "DirEnvioPais": "",
      "dni": "",
      "idTransportista": null,
      "idRetencionEnFuente": "0",
      "isNit": "0",
      "checkDigit": "",
      "countryId": "12",
      "regionId": "0",
      "cityId": "0",
      "idClienteOld": null,
      "idTipoDocto": "3",
      "primerNombre": null,
      "segundoNombre": null,
      "primerApellido": null,
      "segundoApellido": null,
      "record_insert_ts": "2020-08-03 10:28:47",
      "record_update_ts": "2020-08-03 14:48:25",
      "id": "12",
      "code": "AR",
      "name": "Argentina",
      "codigoAFIP": "200",
      "cuitFisica": null,
      "cuitJuridica": null,
      "countryDesc": "Argentina",
      "cityDesc": "",
      "regionDesc": "",
      "retencionFuenteDesc": "",
      "price_list_id": null,
      "idTercero": 6205297
    }
  }
}
```

Server

nginx

Date

Fri, 02 Oct 2020 14:21:07 GMT

Content-Type

application/json; charset=utf-8

Transfer-Encoding

chunked

Connection

keep-alive

Access-Control-Allow-Origin

\*

Access-Control-Allow-Methods

GET,PUT,POST,DELETE,HEAD,OPTIONS

Access-Control-Allow-Headers

Content-Type, Authorization, X-Authorization,X-Requested-With

Allow

GET,HEAD,POST,OPTIONS,TRACE

X-XSS-Protection

1; mode=block

X-Content-Type-Options

nosniff

### POSTListar Cliente

https://staging.colppy.com/lib/frontera2/service.php

## Comprobaciones:

- La sesión es válida (si están activadas las sesiones). Implica que el usuario exista.
- La empresa existe y pertenece al usuario.
- Si El limit viene vacío, entonces se toma por defecto 50.
- Si el start (inicio) viene vacío o es mayor que el limit (límite) se toma por defecto el 0.
- Si el filtro viene vacío, entonces se debe enviar de la siguiente manera : filter:\[\]
- Los parámetros de ordenamiento son obligatorios , si van vacíos se deben pasar de la siguiente manera:
`"order": [{   "field": "RazonSocial",  "dir": "ASC"  }],`
- Si se pasa el order y no se pasan el o los "campos de ordenamiento" (field) entonces no se toma en cuenta el ordenar.

## Errores posibles

- Falta el campo idEmpresa.
- Los parámetros no corresponden a un json válido.
- Error en los parámetros.
- Si se pasa el filtro, los valores obligatorios por cada filtro son field, op y value. Sino retorna error en los parámetros.
- El campo "order" es obligatorio

Bodyraw (json)

View More

json

```json
{
    "auth": {
        "usuario": "<API_USERNAME>",
        "password": "<API_PASSWORD_MD5>"
    },
    "service": {
        "provision": "Cliente",
        "operacion": "listar_cliente"
    },
    "parameters": {
        "sesion": {
            "usuario": "<COLPPY_USERNAME>",
            "claveSesion": ""
        },
        "idEmpresa": "11675",
        "start": 0,
        "limit": 2,
        "filter": [\
            {\
                "field": "Activo",\
                "op": "=",\
                "value": "1"\
            },\
            {\
                "field": "CUIT",\
                "op": "=",\
                "value": "30-69224359-1"\
            },\
            {\
                "field": "FechaAlta",\
                "op": "=",\
                "value": "2012-01-01"\
            },\
            {\
                "field": "NombreFantasia",\
                "op": "=",\
                "value": "TERMOANDES S.A."\
            }\
        ],
        "order": [\
            {\
                "field": "NombreFantasia",\
                "dir": "asc"\
            }\
        ]
    }
}
```

Example Request

Listar Cliente

View More

curl

```curl
curl --location 'https://staging.colppy.com/lib/frontera2/service.php' \
--data '{
    "auth": {
        "usuario": "<API_USERNAME>",
        "password": "<API_PASSWORD_MD5>"
    },
    "service": {
        "provision": "Cliente",
        "operacion": "listar_cliente"
    },
    "parameters": {
        "sesion": {
            "usuario": "<COLPPY_USERNAME>",
            "claveSesion": ""
        },
        "idEmpresa": "11675",
        "start": 0,
        "limit": 2,
        "filter": [\
            {\
                "field": "Activo",\
                "op": "=",\
                "value": "1"\
            },\
            {\
                "field": "CUIT",\
                "op": "=",\
                "value": "30-69224359-1"\
            },\
            {\
                "field": "FechaAlta",\
                "op": "=",\
                "value": "2012-01-01"\
            },\
            {\
                "field": "NombreFantasia",\
                "op": "=",\
                "value": "TERMOANDES S.A."\
            }\
        ],
        "order": [\
            {\
                "field": "NombreFantasia",\
                "dir": "asc"\
            }\
        ]
    }
}'
```

Example Response

- Body
- Headers (0)

No response body

This request doesn't return any response body

No response headers

This request doesn't return any response headers

### POSTLeer Detalle Cliente

https://staging.colppy.com/lib/frontera2/service.php

## Comprobaciones:

- La sesión es válida (si están activadas las sesiones).
- Se comprueba que se pase el id de la empresa.
- Se comprueba que se pase el id de cliente.

## Errores posibles

- ID de empresa faltante.
- ID de cliente faltante.
- No se encuentra el cliente.

Bodyraw (json)

View More

json

```json
{
    "auth": {
        "usuario": "<API_USERNAME>",
        "password": "<API_PASSWORD_MD5>"
    },
    "service": {
        "provision": "Cliente",
        "operacion": "leer_detalle_cliente"
    },
    "parameters": {
        "sesion": {
            "usuario": "<COLPPY_USERNAME>",
            "claveSesion": ""
        },
        "idEmpresa": "11675",
        "idCliente": "3765843"
    }
}
```

Example Request

Leer Detalle Cliente

View More

curl

```curl
curl --location 'https://staging.colppy.com/lib/frontera2/service.php' \
--data '{
    "auth": {
        "usuario": "<API_USERNAME>",
        "password": "<API_PASSWORD_MD5>"
    },
    "service": {
        "provision": "Cliente",
        "operacion": "leer_detalle_cliente"
    },
    "parameters": {
        "sesion": {
            "usuario": "<COLPPY_USERNAME>",
            "claveSesion": ""
        },
        "idEmpresa": "11675",
        "idCliente": "3765843"
    }
}'
```

Example Response

- Body
- Headers (0)

No response body

This request doesn't return any response body

No response headers

This request doesn't return any response headers

### GETNew Request

Example Request

New Request

curl

```curl
curl --location ''
```

Example Response

- Body
- Headers (0)

No response body

This request doesn't return any response body

No response headers

This request doesn't return any response headers

## Contabilidad

Todos los campos mencionados a continuación son enviados al servidor de API en las operaciones de alta\_asiento y editar\_asiento, con el formato de propiedades de un objeto JSON como se muestra en los ejemplos respectivos.
Todos los campos son requeridos y deberán contener nulo ('') en caso de no tener valor.
En la tabla que se muestra a continuación se listan los campos requeridos, su tipo, su valores permitidos y si deben obligatoriamente contener un valor que no sea nulo ('').

| Nombre del campo | Requerimientos |
| --- | --- |
| idEmpresa | Identificador de la.Empresa en todo el sistema. Numérico entero. Obligatorio |
| idAsiento | Identificador del Asiento de la Empresa. Numérico entero. Obligatorio. |
| descAsiento | Alfanumérico. No más largo de 255 caracteres. Obligatorio |
| fechaContable | Formato 'dd-mm-aaaa' o 'dd-mm-aa'. Obligatorio |
| totalDebito | Numérico con decimales. Obligatorio |
| totalCredito | Numérico con decimales. Obligatorio |
| itemsAsiento | Ítems de la factura en forma de Arreglo. Obligatorio. Ver detalle más adelante. |

## Arreglo de Items de Asiento ItemsAsiento

| Nombre del campo | Requerimientos |
| --- | --- |
| idPlanCuenta | Identificador único de la cuenta relacionada |
| Descripcion | Descripción del Plan de cuenta. Obligatorio |
| ccosto1 | Nombre del centro de costos |
| ccosto2 | Nombre del segundo centro de costos |
| Debito | Numérico con decimales. Obligatorio |
| Credito | Numérico con decimales. Obligatorio |
| Comentario | Alfanumérico. No más largo de 255 caracteres. Obligatorio |

## Validaciones que deben pasar los datos antes de enviarlos

- totalDebito = Suma de todos los "Debito" de itemsAsiento
- totalCredito = Suma de todos los "Credito" de itemsAsiento
- totalDebito = totalCredito
- Debe ingresarse por lo menos un ítem de asiento
- La descripción de un Item con importe no puede estar en blanco
- Todos los items deben tener un idPlanCuenta con información

### POSTAlta Asiento

https://staging.colppy.com/lib/frontera2/service.php

Bodyraw (json)

View More

json

```json
{
    "auth": {
        "usuario": "<API_USERNAME>",
        "password": "<API_PASSWORD_MD5>"
    },
    "service": {
        "provision": "Contabilidad",
        "operacion": "alta_asiento"
    },
    "parameters": {
        "sesion": {
            "usuario": "<COLPPY_USERNAME>",
            "claveSesion": ""
        },
        "idUsuario": "a",
        "idAsiento": "",
        "idEmpresa": "11675",
        "fechaContable": "30/06/2020",
        "descAsiento": "Descripcion tested",
        "totalDebito": 100,
        "totalCredito": 100,
        "itemsAsiento": [\
            {\
                "idPlanCuenta": "",\
                "Descripcion": "521116 - Alquileres",\
                "ccosto1": "",\
                "ccosto2": "",\
                "Debito": 100,\
                "Credito": 0,\
                "Comentario": "",\
                "Conciliado": "",\
                "tercero": "",\
                "idTercero": ""\
            },\
            {\
                "idPlanCuenta": "",\
                "Descripcion": "114109 - Adelantos al Personal",\
                "ccosto1": "",\
                "ccosto2": "",\
                "Debito": "0.00",\
                "Credito": 100,\
                "Comentario": "",\
                "Conciliado": "",\
                "tercero": "",\
                "idTercero": ""\
            }\
        ]
    }
}
```

Example Request

Alta Asiento

View More

curl

```curl
curl --location 'https://staging.colppy.com/lib/frontera2/service.php' \
--data '{
    "auth": {
        "usuario": "<API_USERNAME>",
        "password": "<API_PASSWORD_MD5>"
    },
    "service": {
        "provision": "Contabilidad",
        "operacion": "alta_asiento"
    },
    "parameters": {
        "sesion": {
            "usuario": "<COLPPY_USERNAME>",
            "claveSesion": ""
        },
        "idUsuario": "a",
        "idAsiento": "",
        "idEmpresa": "11675",
        "fechaContable": "30/06/2020",
        "descAsiento": "Descripcion tested",
        "totalDebito": 100,
        "totalCredito": 100,
        "itemsAsiento": [\
            {\
                "idPlanCuenta": "",\
                "Descripcion": "521116 - Alquileres",\
                "ccosto1": "",\
                "ccosto2": "",\
                "Debito": 100,\
                "Credito": 0,\
                "Comentario": "",\
                "Conciliado": "",\
                "tercero": "",\
                "idTercero": ""\
            },\
            {\
                "idPlanCuenta": "",\
                "Descripcion": "114109 - Adelantos al Personal",\
                "ccosto1": "",\
                "ccosto2": "",\
                "Debito": "0.00",\
                "Credito": 100,\
                "Comentario": "",\
                "Conciliado": "",\
                "tercero": "",\
                "idTercero": ""\
            }\
        ]
    }
}'
```

Example Response

- Body
- Headers (0)

No response body

This request doesn't return any response body

No response headers

This request doesn't return any response headers

### POSTEditar Asiento

https://staging.colppy.com/lib/frontera2/service.php

Bodyraw (json)

View More

json

```json
{
    "auth": {
        "usuario": "<API_USERNAME>",
        "password": "<API_PASSWORD_MD5>"
    },
    "service": {
        "provision": "Contabilidad",
        "operacion": "alta_asiento"
    },
    "parameters": {
        "sesion": {
            "usuario": "<COLPPY_USERNAME>",
            "claveSesion": ""
        },
        "idUsuario": "a",
        "idAsiento": "",
        "idEmpresa": "11675",
        "fechaContable": "30/06/2020",
        "descAsiento": "Descripcion tested",
        "totalDebito": 100,
        "totalCredito": 100,
        "itemsAsiento": [\
            {\
                "idPlanCuenta": "521116",\
                "Descripcion": "521116 - Alquileres",\
                "ccosto1": "",\
                "ccosto2": "",\
                "Debito": 100,\
                "Credito": 0,\
                "Comentario": "",\
                "Conciliado": "",\
                "tercero": "",\
                "idTercero": ""\
            },\
            {\
                "idPlanCuenta": "114109",\
                "Descripcion": "114109 - Adelantos al Personal",\
                "ccosto1": "",\
                "ccosto2": "",\
                "Debito": "0.00",\
                "Credito": 100,\
                "Comentario": "",\
                "Conciliado": "",\
                "tercero": "",\
                "idTercero": ""\
            }\
        ]
    }
}
```

Example Request

Editar Asiento

View More

curl

```curl
curl --location 'https://staging.colppy.com/lib/frontera2/service.php' \
--data '{
    "auth": {
        "usuario": "<API_USERNAME>",
        "password": "<API_PASSWORD_MD5>"
    },
    "service": {
        "provision": "Contabilidad",
        "operacion": "alta_asiento"
    },
    "parameters": {
        "sesion": {
            "usuario": "<COLPPY_USERNAME>",
            "claveSesion": ""
        },
        "idUsuario": "a",
        "idAsiento": "",
        "idEmpresa": "11675",
        "fechaContable": "30/06/2020",
        "descAsiento": "Descripcion tested",
        "totalDebito": 100,
        "totalCredito": 100,
        "itemsAsiento": [\
            {\
                "idPlanCuenta": "521116",\
                "Descripcion": "521116 - Alquileres",\
                "ccosto1": "",\
                "ccosto2": "",\
                "Debito": 100,\
                "Credito": 0,\
                "Comentario": "",\
                "Conciliado": "",\
                "tercero": "",\
                "idTercero": ""\
            },\
            {\
                "idPlanCuenta": "114109",\
                "Descripcion": "114109 - Adelantos al Personal",\
                "ccosto1": "",\
                "ccosto2": "",\
                "Debito": "0.00",\
                "Credito": 100,\
                "Comentario": "",\
                "Conciliado": "",\
                "tercero": "",\
                "idTercero": ""\
            }\
        ]
    }
}'
```

Example Response

- Body
- Headers (0)

No response body

This request doesn't return any response body

No response headers

This request doesn't return any response headers

### POSTListar Asientos Manuales

https://staging.colppy.com/lib/frontera2/service.php

Campos Requeridos:
"idEmpresa"
"idCliente"

Bodyraw (json)

View More

json

```json
{
    "auth": {
        "usuario": "<API_USERNAME>",
        "password": "<API_PASSWORD_MD5>"
    },
    "service": {
        "provision": "Contabilidad",
        "operacion": "listar_asientosmanuales"
    },
    "parameters": {
        "sesion": {
            "usuario": "<COLPPY_USERNAME>",
            "claveSesion": ""
        },
        "idEmpresa": "11675"
    }
}
```

Example Request

Listar Asientos Manuales

View More

curl

```curl
curl --location 'https://staging.colppy.com/lib/frontera2/service.php' \
--data '{
    "auth": {
        "usuario": "<API_USERNAME>",
        "password": "<API_PASSWORD_MD5>"
    },
    "service": {
        "provision": "Contabilidad",
        "operacion": "listar_asientosmanuales"
    },
    "parameters": {
        "sesion": {
            "usuario": "<COLPPY_USERNAME>",
            "claveSesion": ""
        },
        "idEmpresa": "11675"
    }
}'
```

Example Response

- Body
- Headers (0)

No response body

This request doesn't return any response body

No response headers

This request doesn't return any response headers

### POSTLeer Arbol Contable

https://staging.colppy.com/lib/frontera2/service.php

Campos Requeridos:
"idEmpresa"
"idCliente"

Bodyraw (json)

View More

json

```json
{
    "auth": {
        "usuario": "<API_USERNAME>",
        "password": "<API_PASSWORD_MD5>"
    },
    "service": {
        "provision": "Contabilidad",
        "operacion": "leer_arbol_contabilidad"
    },
    "parameters": {
        "sesion": {
            "usuario": "<COLPPY_USERNAME>",
            "claveSesion": ""
        },
        "idEmpresa": "11675",
        "fechaDesde": "2017-01-01",
        "fechaHasta": "2017-09-25"
    }
}
```

Example Request

Leer Arbol Contable

View More

curl

```curl
curl --location 'https://staging.colppy.com/lib/frontera2/service.php' \
--data '{
    "auth": {
        "usuario": "<API_USERNAME>",
        "password": "<API_PASSWORD_MD5>"
    },
    "service": {
        "provision": "Contabilidad",
        "operacion": "leer_arbol_contabilidad"
    },
    "parameters": {
        "sesion": {
            "usuario": "<COLPPY_USERNAME>",
            "claveSesion": ""
        },
        "idEmpresa": "11675",
        "fechaDesde": "2017-01-01",
        "fechaHasta": "2017-09-25"
    }
}'
```

Example Response

- Body
- Headers (0)

No response body

This request doesn't return any response body

No response headers

This request doesn't return any response headers

### POSTListar cuentas del Diario

https://staging.colppy.com/lib/frontera2/service.php

## Comprobaciones:

- La sesión es válida (si están activadas las sesiones). Implica que el usuario exista.
- La empresa existe y pertenece al usuario.
- En query tiene que ir el daro del idplancuenta que busques, si queres una lista completa se deja vacio como en el ejemplo

## Errores posibles

- Falta el campo idEmpresa

Bodyraw (json)

View More

json

```json
{
    "auth": {
        "usuario": "<API_USERNAME>",
        "password": "<API_PASSWORD_MD5>"
    },
    "service": {
        "provision": "Contabilidad",
        "operacion": "listar_cuentasdiario"
    },
    "parameters": {
        "sesion": {
            "usuario": "<COLPPY_USERNAME>",
            "claveSesion": ""
        },
        "idEmpresa": "11675",
        "query": ""
    }
}
```

Example Request

Ejemplo exitoso

View More

curl

```curl
curl --location 'https://staging.colppy.com/lib/frontera2/service.php' \
--data '{
    "auth": {
        "usuario": "<API_USERNAME>",
        "password": "<API_PASSWORD_MD5>"
    },
    "service": {
        "provision": "Contabilidad",
        "operacion": "listar_cuentasdiario"
    },
    "parameters": {
        "sesion": {
            "usuario": "<COLPPY_USERNAME>",
            "claveSesion": ""
        },
        "idEmpresa": "11675",
        "query": ""
    }
}'
```

200 OK

Example Response

- Body
- Headers (11)

View More

json

```json
{
  "service": {
    "provision": "Contabilidad",
    "operacion": "listar_cuentasdiario",
    "version": "1_0_0_0",
    "response_date": "2020-10-01 17:06:07"
  },
  "result": {
    "estado": 0,
    "mensaje": "La operación se realizó correctamente"
  },
  "response": {
    "success": true,
    "message": "La operación se realizó con éxito.",
    "cuentas": [\
      {\
        "Id": "17X",\
        "idPlanCuenta": "114XXX",\
        "Descripcion": "114XXX - Adelantos al Personal"\
      },\
      {\
        "Id": "11315X",\
        "idPlanCuenta": "311XXX",\
        "Descripcion": "311XXX - Ajuste de Capital"\
      },\
      {\
        "Id": "16X",\
        "idPlanCuenta": "521XXX",\
        "Descripcion": "521XXX - Alquileres"\
      },\
      {\
        "Id": "13X",\
        "idPlanCuenta": "521XXX",\
        "Descripcion": "521XXX - Amortizaciones"\
      }\
    ]
  }
}
```

Server

nginx

Date

Thu, 01 Oct 2020 20:06:07 GMT

Content-Type

application/json; charset=utf-8

Transfer-Encoding

chunked

Connection

keep-alive

Access-Control-Allow-Origin

\*

Access-Control-Allow-Methods

GET,PUT,POST,DELETE,HEAD,OPTIONS

Access-Control-Allow-Headers

Content-Type, Authorization, X-Authorization,X-Requested-With

Allow

GET,HEAD,POST,OPTIONS,TRACE

X-XSS-Protection

1; mode=block

X-Content-Type-Options

nosniff

### POSTListar Movimientos del Diario

https://staging.colppy.com/lib/frontera2/service.php

Campos Requeridos:
"idEmpresa"
"idCliente"

Bodyraw (json)

View More

json

```json
{
    "auth": {
        "usuario": "<API_USERNAME>",
        "password": "<API_PASSWORD_MD5>"
    },
    "service": {
        "provision": "Contabilidad",
        "operacion": "listar_movimientosdiario"
    },
    "parameters": {
        "sesion": {
            "usuario": "<COLPPY_USERNAME>",
            "claveSesion": ""
        },
        "idEmpresa": "11675",
        "fromDate": "2017-01-01",
        "toDate": "2017-09-25"
    }
}
```

Example Request

Listar Movimientos del Diario

View More

curl

```curl
curl --location 'https://staging.colppy.com/lib/frontera2/service.php' \
--data '{
    "auth": {
        "usuario": "<API_USERNAME>",
        "password": "<API_PASSWORD_MD5>"
    },
    "service": {
        "provision": "Contabilidad",
        "operacion": "listar_movimientosdiario"
    },
    "parameters": {
        "sesion": {
            "usuario": "<COLPPY_USERNAME>",
            "claveSesion": ""
        },
        "idEmpresa": "11675",
        "fromDate": "2017-01-01",
        "toDate": "2017-09-25"
    }
}'
```

Example Response

- Body
- Headers (0)

No response body

This request doesn't return any response body

No response headers

This request doesn't return any response headers

## Empresa

### POSTAlta Empresa

https://staging.colppy.com/lib/frontera2/service.php

Servicio para crear un empresa

Bodyraw (json)

View More

json

```json
{
    "auth": {
        "usuario": "<API_USERNAME>",
        "password": "<API_PASSWORD_MD5>"
    },
    "service": {
        "provision": "Empresa",
        "operacion": "alta_empresa"
    },
    "parameters": {
        "sesion": {
            "usuario": "<COLPPY_USERNAME>",
            "claveSesion": ""
        },
        "datos_generales": {
            "idUsuario": "a",
            "Nombre": "Test172",
            "razonSocial": "Test172",
            "domicilio": "Abc 123 - CABA",
            "localidad": "CABA",
            "codigoPostal": "1422",
            "provincia": "Catamarca",
            "pais": "Test172",
            "telefono": "Test172",
            "email": "a@a.com",
            "CUIT": "00-00000000-0",
            "nroIIBB": "767",
            "monotributo": "1",
            "idEmpresa": "",
            "idCondicionIva": "2",
            "tipoOperacion": "2"
        }
    }
}
```

Example Request

Alta Empresa

View More

curl

```curl
curl --location 'https://staging.colppy.com/lib/frontera2/service.php' \
--data-raw '{
    "auth": {
        "usuario": "<API_USERNAME>",
        "password": "<API_PASSWORD_MD5>"
    },
    "service": {
        "provision": "Empresa",
        "operacion": "alta_empresa"
    },
    "parameters": {
        "sesion": {
            "usuario": "<COLPPY_USERNAME>",
            "claveSesion": ""
        },
        "datos_generales": {
            "idUsuario": "a",
            "Nombre": "Test172",
            "razonSocial": "Test172",
            "domicilio": "Abc 123 - CABA",
            "localidad": "CABA",
            "codigoPostal": "1422",
            "provincia": "Catamarca",
            "pais": "Test172",
            "telefono": "Test172",
            "email": "a@a.com",
            "CUIT": "00-00000000-0",
            "nroIIBB": "767",
            "monotributo": "1",
            "idEmpresa": "",
            "idCondicionIva": "2",
            "tipoOperacion": "2"
        }
    }
}'
```

Example Response

- Body
- Headers (0)

No response body

This request doesn't return any response body

No response headers

This request doesn't return any response headers

### POSTEditar Empresa

https://staging.colppy.com/lib/frontera2/service.php

Servicio para crear un empresa

Bodyraw (json)

View More

json

```json
{
    "auth": {
        "usuario": "<API_USERNAME>",
        "password": "<API_PASSWORD_MD5>"
    },
    "service": {
        "provision": "Empresa",
        "operacion": "editar_empresa"
    },
    "parameters": {
        "sesion": {
            "usuario": "<COLPPY_USERNAME>",
            "claveSesion": ""
        },
        "datos_generales": {
            "idEmpresa": "44907",
            "Nombre": "Test172",
            "razonSocial": "Test172",
            "nroIIBB": "exento",
            "CUIT": "00-00000000-0",
            "domicilio": "BONIFACIO JOSE 3550",
            "codigoPostal": "1407",
            "localidad": "CP: C1072AAL",
            "provincia": "CABA",
            "pais": "Argentina",
            "telefono": "110000006",
            "email": "dario.rebora@colppy.com",
            "cbu": "",
            "monotributo": "1",
            "idCondicionIva": "1",
            "impgan": "1",
            "countryId": "12",
            "fecha_cierre_impuesto": "2000-11-01",
            "idAdministradora": ""
        }
    }
}
```

Example Request

Editar Empresa

View More

curl

```curl
curl --location 'https://staging.colppy.com/lib/frontera2/service.php' \
--data-raw '{
    "auth": {
        "usuario": "<API_USERNAME>",
        "password": "<API_PASSWORD_MD5>"
    },
    "service": {
        "provision": "Empresa",
        "operacion": "editar_empresa"
    },
    "parameters": {
        "sesion": {
            "usuario": "<COLPPY_USERNAME>",
            "claveSesion": ""
        },
        "datos_generales": {
            "idEmpresa": "44907",
            "Nombre": "Test172",
            "razonSocial": "Test172",
            "nroIIBB": "exento",
            "CUIT": "00-00000000-0",
            "domicilio": "BONIFACIO JOSE 3550",
            "codigoPostal": "1407",
            "localidad": "CP: C1072AAL",
            "provincia": "CABA",
            "pais": "Argentina",
            "telefono": "110000006",
            "email": "dario.rebora@colppy.com",
            "cbu": "",
            "monotributo": "1",
            "idCondicionIva": "1",
            "impgan": "1",
            "countryId": "12",
            "fecha_cierre_impuesto": "2000-11-01",
            "idAdministradora": ""
        }
    }
}'
```

Example Response

- Body
- Headers (0)

No response body

This request doesn't return any response body

No response headers

This request doesn't return any response headers

### POSTLeer Empresa

https://staging.colppy.com/lib/frontera2/service.php

Servicio para crear un empresa

Bodyraw (json)

View More

json

```json
{
    "auth": {
        "usuario": "<API_USERNAME>",
        "password": "<API_PASSWORD_MD5>"
    },
    "service": {
        "provision": "Empresa",
        "operacion": "leer_empresa"
    },
    "parameters": {
        "sesion": {
            "usuario": "<COLPPY_USERNAME>",
            "claveSesion": ""
        },
        "idEmpresa": "11675"
    }
}
```

Example Request

Leer Empresa

View More

curl

```curl
curl --location 'https://staging.colppy.com/lib/frontera2/service.php' \
--data '{
    "auth": {
        "usuario": "<API_USERNAME>",
        "password": "<API_PASSWORD_MD5>"
    },
    "service": {
        "provision": "Empresa",
        "operacion": "leer_empresa"
    },
    "parameters": {
        "sesion": {
            "usuario": "<COLPPY_USERNAME>",
            "claveSesion": ""
        },
        "idEmpresa": "11675"
    }
}'
```

Example Response

- Body
- Headers (0)

No response body

This request doesn't return any response body

No response headers

This request doesn't return any response headers

### POSTLeer Talonario

https://staging.colppy.com/lib/frontera2/service.php

Servicio para crear un empresa

Bodyraw (json)

View More

json

```json
{
    "auth": {
        "usuario": "<API_USERNAME>",
        "password": "<API_PASSWORD_MD5>"
    },
    "service": {
        "provision": "Empresa",
        "operacion": "leer_talonario"
    },
    "parameters": {
        "sesion": {
            "usuario": "<COLPPY_USERNAME>",
            "claveSesion": ""
        },
        "talonarioDefault": 1,
        "descTipoComprobante": "",
        "idEmpresa": "11675"
    }
}
```

Example Request

Leer Talonario

View More

curl

```curl
curl --location 'https://staging.colppy.com/lib/frontera2/service.php' \
--data '{
    "auth": {
        "usuario": "<API_USERNAME>",
        "password": "<API_PASSWORD_MD5>"
    },
    "service": {
        "provision": "Empresa",
        "operacion": "leer_talonario"
    },
    "parameters": {
        "sesion": {
            "usuario": "<COLPPY_USERNAME>",
            "claveSesion": ""
        },
        "talonarioDefault": 1,
        "descTipoComprobante": "",
        "idEmpresa": "11675"
    }
}'
```

Example Response

- Body
- Headers (0)

No response body

This request doesn't return any response body

No response headers

This request doesn't return any response headers

### POSTLeer Numero Recibo

https://staging.colppy.com/lib/frontera2/service.php

Servicio para crear un empresa

Bodyraw (json)

View More

json

```json
{
    "auth": {
        "usuario": "<API_USERNAME>",
        "password": "<API_PASSWORD_MD5>"
    },
    "service": {
        "provision": "Empresa",
        "operacion": "leer_numero_recibo"
    },
    "parameters": {
        "sesion": {
            "usuario": "<COLPPY_USERNAME>",
            "claveSesion": ""
        },
        "idEmpresa": "11675",
        "prefijo": "0"
    }
}
```

Example Request

Leer Numero Recibo

View More

curl

```curl
curl --location 'https://staging.colppy.com/lib/frontera2/service.php' \
--data '{
    "auth": {
        "usuario": "<API_USERNAME>",
        "password": "<API_PASSWORD_MD5>"
    },
    "service": {
        "provision": "Empresa",
        "operacion": "leer_numero_recibo"
    },
    "parameters": {
        "sesion": {
            "usuario": "<COLPPY_USERNAME>",
            "claveSesion": ""
        },
        "idEmpresa": "11675",
        "prefijo": "0"
    }
}'
```

Example Response

- Body
- Headers (0)

No response body

This request doesn't return any response body

No response headers

This request doesn't return any response headers

### POSTProximo numero factura

https://staging.colppy.com/lib/frontera2/service.php

Servicio para crear un empresa

Bodyraw (json)

View More

json

```json
{
    "auth": {
        "usuario": "<API_USERNAME>",
        "password": "<API_PASSWORD_MD5>"
    },
    "service": {
        "provision": "Empresa",
        "operacion": "proximo_numero_factura"
    },
    "parameters": {
        "sesion": {
            "usuario": "<COLPPY_USERNAME>",
            "claveSesion": ""
        },
        "idEmpresa": "11675",
        "prefijo": "0000",
        "tipofactura": "A",
        "tipocomprobante": "4",
        "recurrente": ""
    }
}
```

Example Request

Proximo numero factura

View More

curl

```curl
curl --location 'https://staging.colppy.com/lib/frontera2/service.php' \
--data '{
    "auth": {
        "usuario": "<API_USERNAME>",
        "password": "<API_PASSWORD_MD5>"
    },
    "service": {
        "provision": "Empresa",
        "operacion": "proximo_numero_factura"
    },
    "parameters": {
        "sesion": {
            "usuario": "<COLPPY_USERNAME>",
            "claveSesion": ""
        },
        "idEmpresa": "11675",
        "prefijo": "0000",
        "tipofactura": "A",
        "tipocomprobante": "4",
        "recurrente": ""
    }
}'
```

Example Response

- Body
- Headers (0)

No response body

This request doesn't return any response body

No response headers

This request doesn't return any response headers

### POSTProximo numero Remito

https://staging.colppy.com/lib/frontera2/service.php

Servicio para crear un empresa

Bodyraw (json)

View More

json

```json
{
    "auth": {
        "usuario": "<API_USERNAME>",
        "password": "<API_PASSWORD_MD5>"
    },
    "service": {
        "provision": "Empresa",
        "operacion": "proximo_numero_remito"
    },
    "parameters": {
        "sesion": {
            "usuario": "<COLPPY_USERNAME>",
            "claveSesion": ""
        },
        "idEmpresa": "11675",
        "prefijo": "0780"
    }
}
```

Example Request

Proximo numero Remito

View More

curl

```curl
curl --location 'https://staging.colppy.com/lib/frontera2/service.php' \
--data '{
    "auth": {
        "usuario": "<API_USERNAME>",
        "password": "<API_PASSWORD_MD5>"
    },
    "service": {
        "provision": "Empresa",
        "operacion": "proximo_numero_remito"
    },
    "parameters": {
        "sesion": {
            "usuario": "<COLPPY_USERNAME>",
            "claveSesion": ""
        },
        "idEmpresa": "11675",
        "prefijo": "0780"
    }
}'
```

Example Response

- Body
- Headers (0)

No response body

This request doesn't return any response body

No response headers

This request doesn't return any response headers

### POSTListar Empresas

https://staging.colppy.com/lib/frontera2/service.php

Servicio para crear un empresa

Bodyraw (json)

View More

json

```json
{
    "auth": {
        "usuario": "<API_USERNAME>",
        "password": "<API_PASSWORD_MD5>"
    },
    "service": {
        "provision": "Empresa",
        "operacion": "listar_empresa"
    },
    "parameters": {
        "sesion": {
            "usuario": "<COLPPY_USERNAME>",
            "claveSesion": ""
        },
        "start": 0,
        "limit": 10
    },
    "filter": [{\
        "field": "IdEmpresa",\
        "op": "<>",\
        "value": "1"\
    }],
    "order": {
        "field": ["IdEmpresa"],
        "order": "asc"
    }
}
```

Example Request

Listar Empresas

View More

curl

```curl
curl --location 'https://staging.colppy.com/lib/frontera2/service.php' \
--data '{
    "auth": {
        "usuario": "<API_USERNAME>",
        "password": "<API_PASSWORD_MD5>"
    },
    "service": {
        "provision": "Empresa",
        "operacion": "listar_empresa"
    },
    "parameters": {
        "sesion": {
            "usuario": "<COLPPY_USERNAME>",
            "claveSesion": ""
        },
        "start": 0,
        "limit": 10
    },
    "filter": [{\
        "field": "IdEmpresa",\
        "op": "<>",\
        "value": "1"\
    }],
    "order": {
        "field": ["IdEmpresa"],
        "order": "asc"
    }
}'
```

Example Response

- Body
- Headers (0)

No response body

This request doesn't return any response body

No response headers

This request doesn't return any response headers

### POSTListar Centros de costos

https://staging.colppy.com/lib/frontera2/service.php

- La sesión es válida (si están activadas las sesiones). Implica que el usuario exista.
- La empresa existe y pertenece al usuario.
- ccosto debe ser igual a 1 o 2

Bodyraw (json)

View More

json

```json
{
    "auth": {
        "usuario": "<API_USERNAME>",
        "password": "<API_PASSWORD_MD5>"
    },
    "service": {
        "provision": "Empresa",
        "operacion": "listar_ccostos"
    },
    "parameters": {
        "sesion": {
            "usuario": "<COLPPY_USERNAME>",
            "claveSesion": ""
        },
        "idEmpresa": "11675",
    	"ccosto": 1
    }
}
```

Example Request

Listar Centros de costos

View More

curl

```curl
curl --location 'https://staging.colppy.com/lib/frontera2/service.php' \
--data '{
    "auth": {
        "usuario": "<API_USERNAME>",
        "password": "<API_PASSWORD_MD5>"
    },
    "service": {
        "provision": "Empresa",
        "operacion": "listar_ccostos"
    },
    "parameters": {
        "sesion": {
            "usuario": "<COLPPY_USERNAME>",
            "claveSesion": ""
        },
        "idEmpresa": "11675",
    	"ccosto": 1
    }
}'
```

Example Response

- Body
- Headers (0)

No response body

This request doesn't return any response body

No response headers

This request doesn't return any response headers

### POSThttps://login.colppy.com/resources/php/paneldecontrol/TC\_graficoResultados.php

https://login.colppy.com/resources/php/paneldecontrol/TC\_graficoResultados.php

HEADERS

User-Agent

Mozilla/5.0 (X11; Ubuntu; Linux x86\_64; rv:109.0) Gecko/20100101 Firefox/119.0

Accept

\*/\*

Accept-Language

es-AR,es;q=0.5

Accept-Encoding

gzip, deflate, br

X-Requested-With

XMLHttpRequest

Content-Type

application/x-www-form-urlencoded; charset=UTF-8

Origin

https://login.colppy.com

Connection

keep-alive

Referer

https://login.colppy.com/

Cookie

[REDACTED - credentials must not be committed]

Sec-Fetch-Dest

empty

Sec-Fetch-Mode

cors

Sec-Fetch-Site

same-origin

TE

trailers

Bodyraw

```javascript
idEmpresa=13145&modo=M
```

Example Request

https://login.colppy.com/resources/php/paneldecontrol/TC\_graficoResultados.php

View More

curl

```curl
curl --location 'https://login.colppy.com/resources/php/paneldecontrol/TC_graficoResultados.php' \
--header 'User-Agent: Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:109.0) Gecko/20100101 Firefox/119.0' \
--header 'Accept: */*' \
--header 'Accept-Language: es-AR,es;q=0.5' \
--header 'Accept-Encoding: gzip, deflate, br' \
--header 'X-Requested-With: XMLHttpRequest' \
--header 'Content-Type: application/x-www-form-urlencoded; charset=UTF-8' \
--header 'Origin: https://login.colppy.com' \
--header 'Connection: keep-alive' \
--header 'Referer: https://login.colppy.com/' \
--header 'Cookie: [REDACTED - credentials must not be committed]' \
--header 'Sec-Fetch-Dest: empty' \
--header 'Sec-Fetch-Mode: cors' \
--header 'Sec-Fetch-Site: same-origin' \
--header 'TE: trailers' \
--data 'idEmpresa=13145&modo=M'
```

Example Response

- Body
- Headers (0)

No response body

This request doesn't return any response body

No response headers

This request doesn't return any response headers