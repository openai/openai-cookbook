Atlassian uses cookies to improve your browsing experience, perform analytics and research, and conduct advertising. Accept all cookies to indicate that you agree to our use of cookies on your device. [Atlassian cookies and tracking notice, (opens new window)](https://www.atlassian.com/legal/cookies)

PreferencesOnly necessaryAccept all

Collapse sidebar

Switch sites or apps

[![](https://colppy.atlassian.net/wiki/download/attachments/524289/atl.site.logo?version=5&modificationDate=1733246707398&cacheVersion=1&api=v2)\\
\\
![](https://colppy.atlassian.net/wiki/download/attachments/524289/atl.site.logo?version=5&modificationDate=1733246707398&cacheVersion=1&api=v2)](https://colppy.atlassian.net/wiki)

Colppy Wiki

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









  - [Inicio de sesión](https://colppy.atlassian.net/wiki/spaces/CA/pages/16318471/Inicio+de+sesi+n)
- [Listado de Provisiones y Operaciones Disponibles](https://colppy.atlassian.net/wiki/spaces/CA/pages/16318473/Listado+de+Provisiones+y+Operaciones+Disponibles)

- [APÉNDICE](https://colppy.atlassian.net/wiki/spaces/CA/pages/9896077/AP+NDICE)

- [Ayuda](https://colppy.atlassian.net/wiki/spaces/CA/pages/3165028353/Ayuda)


Space apps

[draw.io Diagrams](https://colppy.atlassian.net/wiki/display/CA/customcontent/list/ac%3Acom.mxgraph.confluence.plugins.diagramly%3Adrawio-diagram)

![](https://ac.draw.io/images/drawlogo48.png)

* * *

You‘re viewing this with anonymous access, so some content might be blocked.

Close

Colppy API

/

Inicio de sesión

[Updated Sept 30, 2025](https://colppy.atlassian.net/wiki/spaces/CA/history/16318471)

More actions

# Inicio de sesión

![](https://colppy.atlassian.net/wiki/aa-avatar/5c51def617a8567a2ba83873)

By Former user (Deleted)

1 min

Add a reaction

**¿Cuáles son las URL?**

**Produccion:** https://login.colppy.com/lib/frontera2/service.php

**Staging:** https://staging.colppy.com/lib/frontera2/service.php (Demora 24 Hs desde la creación del usuario en la web de desarrolladores en estar disponible).

**¿Cuál es el JSON de inicio de sesión?**

##### **Operación iniciar\_sesion**

`{
    "auth": {
        "usuario": "xxxx@colppy.com", // Usuario registrado en dev.colppy.com.
        "password": "egewew6ewg6ew6363" // Contraseña del usuario registrado en dev.colppy.com en formato MD5.
    },
    "service": {
        "provision": "Usuario",
        "operacion": "iniciar_sesion"
    },
    "parameters": {
        "usuario": "xxxx@colppy.com", // Usuario de Colppy.
        "password": "egewew6ewg6ew6363" // Contraseña del usuario de Colppy en formato MD5.
    }
}`

El JSON se divide en tres partes **auth**, **service** y **parameters.**

En **auth** van tus credenciales, es decir, tu usuario con el que te registraste en api.colppy.com y la contraseña en formato MD5.

En **service** se especifica la provisión y la operación que deseo hacer. Se pueden ver todas las opciones [aquí.](https://colppy.atlassian.net/wiki/spaces/CA/pages/16318473 "https://colppy.atlassian.net/wiki/spaces/CA/pages/16318473") El nombre de las provisiones y operaciones son sensibles a mayúsculas.

En **parameters** van los parámetrosque espera la operación para poderse ejecutar. Estos parámetros varían dependiendo la operación que necesitemos hacer.

Una vez que ejecutamos la petición POST con nuestro JSON, Colppy API nos va a responder con un mensaje informándonos si el requerimiento se realizó con éxito o no.

**Ejemplo:**

##### **Response**

`{
      "service":{
            "provision":"Usuario",
            "operacion":"iniciar_sesion",
            "version":"1_0_0_0",
            "response_date":"2014-24-06 17:10:19"
      },
      "result":{
            "estado":0,
            "mensaje":"La operaci\u00f3n se realiz\u00f3 correctamente"
      },
      "response":{
            "success":true,
            "message":"La operacion se realizo con exito.",
            "data":{
                  "claveSesion":"b5a97564ad59e624a6ba545ecd3ca112"
            }
      }
}`

Del response nos quedamos con la **"claveSesion"** que es obligatoria para realizar otras operaciones.

Collapse action bar

Open Comments Panel

Open Details Panel

Rovo Button

{"serverDuration": 69, "requestCorrelationId": "b1ddd3e7fefe443a8b990cd803f5a6ed"}