[Skip to main content](https://pypi.org/project/colppy-api/#content) Switch to mobile version

[![PyPI](https://pypi.org/static/images/logo-small.8998e9d1.svg)](https://pypi.org/)

Search PyPISearch

- [Help](https://pypi.org/help/)
- [Docs](https://docs.pypi.org/)
- [Sponsors](https://pypi.org/sponsors/)
- [Log in](https://pypi.org/account/login/?next=https%3A%2F%2Fpypi.org%2Fproject%2Fcolppy-api%2F)
- [Register](https://pypi.org/account/register/)

Menu

- [Help](https://pypi.org/help/)
- [Docs](https://docs.pypi.org/)
- [Sponsors](https://pypi.org/sponsors/)
- [Log in](https://pypi.org/account/login/?next=https%3A%2F%2Fpypi.org%2Fproject%2Fcolppy-api%2F)
- [Register](https://pypi.org/account/register/)

Search PyPISearch

# colppy-api 1.2.2

pip install colppy-apiCopy PIP instructions

[Latest version](https://pypi.org/project/colppy-api/)

Released: Mar 12, 2025

Cliente API para Colppy (NO OFICIAL)

### Navigation

- [Project description](https://pypi.org/project/colppy-api/#description)
- [Release history](https://pypi.org/project/colppy-api/#history)
- [Download files](https://pypi.org/project/colppy-api/#files)

### Verified details

_These details have been [verified by PyPI](https://docs.pypi.org/project_metadata/#verified-details)_

###### Maintainers

[![Avatar for juanmanuelpanozzoz from gravatar.com](https://pypi-camo.freetls.fastly.net/a07d728d4206c643fb6b93f9f251d825ee08e7c1/68747470733a2f2f7365637572652e67726176617461722e636f6d2f6176617461722f39636234383232356336373161396363616530656430323063656464376537313f73697a653d3530)juanmanuelpanozzoz](https://pypi.org/user/juanmanuelpanozzoz/)[![Avatar for SilviaRusMata from gravatar.com](https://pypi-camo.freetls.fastly.net/6f153526a862d558328aa35d42427f092c2dbcb1/68747470733a2f2f7365637572652e67726176617461722e636f6d2f6176617461722f30353739623337636366616164313530636263653864633636303864396635343f73697a653d3530)SilviaRusMata](https://pypi.org/user/SilviaRusMata/)[![Avatar for tomigroovin from gravatar.com](https://pypi-camo.freetls.fastly.net/2b457b49176142189bff43040830ba8bb991e243/68747470733a2f2f7365637572652e67726176617461722e636f6d2f6176617461722f38643064393033643539323066663562346233623131353164366164626532343f73697a653d3530)tomigroovin](https://pypi.org/user/tomigroovin/)

###### Meta

- **Author:** [Groovinads](mailto:juanmanuel.panozzo@groovinads.com)

### Unverified details

_These details have **not** been verified by PyPI_

###### Project links

- [Homepage](https://bitbucket.org/groovinads/colppi-api)
- [Issues](https://bitbucket.org/groovinads/colppi-api/issues)

###### Meta

- **License:** MIT

- Tags
api
,
client
,
colppy

- **Requires:** Python >=3.10


###### Classifiers

- **Operating System**  - [OS Independent](https://pypi.org/search/?c=Operating+System+%3A%3A+OS+Independent)
- **Programming Language**  - [Python :: 3](https://pypi.org/search/?c=Programming+Language+%3A%3A+Python+%3A%3A+3)
  - [Python :: 3.11](https://pypi.org/search/?c=Programming+Language+%3A%3A+Python+%3A%3A+3.11)

[Report project as malware](https://pypi.org/project/colppy-api/submit-malware-report/)

- [Project description](https://pypi.org/project/colppy-api/#description)
- [Project details](https://pypi.org/project/colppy-api/#data)
- [Release history](https://pypi.org/project/colppy-api/#history)
- [Download files](https://pypi.org/project/colppy-api/#files)

## Project description

# Colppy API Client

Cliente Python para la API de Colppy, sistema de gestión contable y financiera.

## Instalación

```
pip install colppy-api
```

## Configuración

El paquete incluye una CLI para facilitar la configuración inicial:

```
# Crear archivo de configuración interactivamente
colppy-api init
```

O puedes crear manualmente un archivo `config.json` en el directorio raíz de tu proyecto:

```
{
  "ColppyAPI": {
    "COLPPY_API_URI": "https://login.colppy.com/lib/frontera2/service.php",
    "COLPPY_AUTH_USER": "tu_usuario",
    "COLPPY_AUTH_PASSWORD": "tu_password",
    "COLPPY_PARAMS_USER": "tu_usuario_params",
    "COLPPY_PARAMS_PASSWORD": "tu_password_params"
  },
  "LogLevel": {
    "LOG_LEVEL": "DEBUG"
  }
}
```

## Uso Básico

```
from colppy import ColppyAPIClient

async def main():
    # Inicializar cliente
    client = ColppyAPIClient()
    await client.get_token()

    # Ejemplo: Obtener empresas
    empresas = await client.get_empresas()

    await client.logout()

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
```

## Funcionalidades Principales

- Gestión de empresas
- Gestión de clientes
- Gestión de proveedores
- Comprobantes de compra y venta
- Movimientos contables
- Manejo de sesiones

## Tipos de Comprobantes

| ID | Código | Descripción |
| --- | --- | --- |
| 1 | FAC | Factura de Compra |
| 2 | NCC | Nota de Crédito Compra |
| 3 | NDC | Nota de Débito Compra |
| 4 | FAV | Factura de Venta |
| 5 | NCV | Nota de Crédito Venta |
| 6 | NDV | Nota de Débito Venta |
| 7 | FCC | Factura Compra Contado |
| 8 | FVC | Factura Venta Contado |

## Desarrollo

Para contribuir al desarrollo:

```
# Clonar repositorio
git clone https://github.com/groovinads/colppy-api.git

# Crear entorno virtual
python -m venv .venv

# Activar entorno virtual
source .venv/bin/activate  # Linux/Mac
.venv\Scripts\activate     # Windows

# Instalar en modo desarrollo
pip install -e .
```

### Scripts de Desarrollo

```
# Publicar en PyPI
python scripts/run.py publish

# Limpiar caché
python scripts/run.py clean-cache

# Limpiar proyecto
python scripts/run.py clean

# Ejecutar todo
python scripts/run.py all
```

### Comandos CLI

```
# Inicializar configuración
colppy-api init

# Ver ayuda
colppy-api --help
```

## Licencia

MIT License

## Project details

### Verified details

_These details have been [verified by PyPI](https://docs.pypi.org/project_metadata/#verified-details)_

###### Maintainers

[![Avatar for juanmanuelpanozzoz from gravatar.com](https://pypi-camo.freetls.fastly.net/a07d728d4206c643fb6b93f9f251d825ee08e7c1/68747470733a2f2f7365637572652e67726176617461722e636f6d2f6176617461722f39636234383232356336373161396363616530656430323063656464376537313f73697a653d3530)juanmanuelpanozzoz](https://pypi.org/user/juanmanuelpanozzoz/)[![Avatar for SilviaRusMata from gravatar.com](https://pypi-camo.freetls.fastly.net/6f153526a862d558328aa35d42427f092c2dbcb1/68747470733a2f2f7365637572652e67726176617461722e636f6d2f6176617461722f30353739623337636366616164313530636263653864633636303864396635343f73697a653d3530)SilviaRusMata](https://pypi.org/user/SilviaRusMata/)[![Avatar for tomigroovin from gravatar.com](https://pypi-camo.freetls.fastly.net/2b457b49176142189bff43040830ba8bb991e243/68747470733a2f2f7365637572652e67726176617461722e636f6d2f6176617461722f38643064393033643539323066663562346233623131353164366164626532343f73697a653d3530)tomigroovin](https://pypi.org/user/tomigroovin/)

###### Meta

- **Author:** [Groovinads](mailto:juanmanuel.panozzo@groovinads.com)

### Unverified details

_These details have **not** been verified by PyPI_

###### Project links

- [Homepage](https://bitbucket.org/groovinads/colppi-api)
- [Issues](https://bitbucket.org/groovinads/colppi-api/issues)

###### Meta

- **License:** MIT

- Tags
api
,
client
,
colppy

- **Requires:** Python >=3.10


###### Classifiers

- **Operating System**  - [OS Independent](https://pypi.org/search/?c=Operating+System+%3A%3A+OS+Independent)
- **Programming Language**  - [Python :: 3](https://pypi.org/search/?c=Programming+Language+%3A%3A+Python+%3A%3A+3)
  - [Python :: 3.11](https://pypi.org/search/?c=Programming+Language+%3A%3A+Python+%3A%3A+3.11)

## Release history[Release notifications](https://pypi.org/help/\#project-release-notifications) \|  [RSS feed](https://pypi.org/rss/project/colppy-api/releases.xml)

This version

![](https://pypi.org/static/images/blue-cube.572a5bfb.svg)

[1.2.2\\
\\
\\
Mar 12, 2025](https://pypi.org/project/colppy-api/1.2.2/)

![](https://pypi.org/static/images/white-cube.2351a86c.svg)

[1.2.1\\
\\
\\
Feb 28, 2025](https://pypi.org/project/colppy-api/1.2.1/)

![](https://pypi.org/static/images/white-cube.2351a86c.svg)

[1.1.9.1\\
\\
\\
Feb 28, 2025](https://pypi.org/project/colppy-api/1.1.9.1/)

![](https://pypi.org/static/images/white-cube.2351a86c.svg)

[1.1.9\\
\\
\\
Feb 28, 2025](https://pypi.org/project/colppy-api/1.1.9/)

![](https://pypi.org/static/images/white-cube.2351a86c.svg)

[1.1.8\\
\\
\\
Feb 26, 2025](https://pypi.org/project/colppy-api/1.1.8/)

![](https://pypi.org/static/images/white-cube.2351a86c.svg)

[1.1.7\\
\\
\\
Feb 24, 2025](https://pypi.org/project/colppy-api/1.1.7/)

![](https://pypi.org/static/images/white-cube.2351a86c.svg)

[1.1.6\\
\\
\\
Feb 19, 2025](https://pypi.org/project/colppy-api/1.1.6/)

![](https://pypi.org/static/images/white-cube.2351a86c.svg)

[1.1.5\\
\\
\\
Feb 19, 2025](https://pypi.org/project/colppy-api/1.1.5/)

![](https://pypi.org/static/images/white-cube.2351a86c.svg)

[1.1.4\\
\\
\\
Feb 14, 2025](https://pypi.org/project/colppy-api/1.1.4/)

![](https://pypi.org/static/images/white-cube.2351a86c.svg)

[1.1.3\\
\\
\\
Feb 7, 2025](https://pypi.org/project/colppy-api/1.1.3/)

![](https://pypi.org/static/images/white-cube.2351a86c.svg)

[1.1.2\\
\\
\\
Feb 4, 2025](https://pypi.org/project/colppy-api/1.1.2/)

![](https://pypi.org/static/images/white-cube.2351a86c.svg)

[1.1.1\\
\\
\\
Feb 4, 2025](https://pypi.org/project/colppy-api/1.1.1/)

![](https://pypi.org/static/images/white-cube.2351a86c.svg)

[1.1.0\\
\\
\\
Jan 31, 2025](https://pypi.org/project/colppy-api/1.1.0/)

![](https://pypi.org/static/images/white-cube.2351a86c.svg)

[1.0.1\\
\\
\\
Jan 13, 2025](https://pypi.org/project/colppy-api/1.0.1/)

![](https://pypi.org/static/images/white-cube.2351a86c.svg)

[1.0.0\\
\\
\\
Jan 6, 2025](https://pypi.org/project/colppy-api/1.0.0/)

## Download files

Download the file for your platform. If you're not sure which to choose, learn more about [installing packages](https://packaging.python.org/tutorials/installing-packages/ "External link").

### Source Distribution

[colppy\_api-1.2.2.tar.gz](https://files.pythonhosted.org/packages/b2/00/02bfb5d0e40852d12e5644eee751239daad4a30dd0e0e87210daab60a4e9/colppy_api-1.2.2.tar.gz)
(33.3 kB
[view details](https://pypi.org/project/colppy-api/#colppy_api-1.2.2.tar.gz))


Uploaded Mar 12, 2025`Source`

### Built Distribution

Filter files by name, interpreter, ABI, and platform.

If you're not sure about the file name format, learn more about [wheel file names](https://packaging.python.org/en/latest/specifications/binary-distribution-format/ "External link").

Copy a direct link to the current filters [https://pypi.org/project/colppy-api/#files](https://pypi.org/project/colppy-api/#files)
Copy

Showing 1 of 1 file.

File name

InterpreterInterpreterpy3

ABIABInone

PlatformPlatformany

[colppy\_api-1.2.2-py3-none-any.whl](https://files.pythonhosted.org/packages/be/c3/6a50952afaffe50b8cda65938eb2b3923ff18cbf7a9a42d7b66bdba76785/colppy_api-1.2.2-py3-none-any.whl)
(31.0 kB
[view details](https://pypi.org/project/colppy-api/#colppy_api-1.2.2-py3-none-any.whl))


Uploaded Mar 12, 2025`Python 3`

## File details

Details for the file `colppy_api-1.2.2.tar.gz`.


### File metadata

- Download URL: [colppy\_api-1.2.2.tar.gz](https://files.pythonhosted.org/packages/b2/00/02bfb5d0e40852d12e5644eee751239daad4a30dd0e0e87210daab60a4e9/colppy_api-1.2.2.tar.gz)
- Upload date: Mar 12, 2025
- Size: 33.3 kB
- Tags: Source
- Uploaded using Trusted Publishing? No
- Uploaded via: twine/6.1.0 CPython/3.10.16

### File hashes

| Algorithm | Hash digest |  |
| --- | --- | --- |
| SHA256 | `f2d44911327e8c37c2c5f19d6c28a550ec040e4a62da5fc777fcc62f1799dec7` | Copy |
| MD5 | `6cadae27b2d9c375fd73a489c2391d42` | Copy |
| BLAKE2b-256 | `b20002bfb5d0e40852d12e5644eee751239daad4a30dd0e0e87210daab60a4e9` | Copy |

Hashes for colppy\_api-1.2.2.tar.gz

[See more details on using hashes here.](https://pip.pypa.io/en/stable/topics/secure-installs/#hash-checking-mode "External link")

## File details

Details for the file `colppy_api-1.2.2-py3-none-any.whl`.


### File metadata

- Download URL: [colppy\_api-1.2.2-py3-none-any.whl](https://files.pythonhosted.org/packages/be/c3/6a50952afaffe50b8cda65938eb2b3923ff18cbf7a9a42d7b66bdba76785/colppy_api-1.2.2-py3-none-any.whl)
- Upload date: Mar 12, 2025
- Size: 31.0 kB
- Tags: Python 3
- Uploaded using Trusted Publishing? No
- Uploaded via: twine/6.1.0 CPython/3.10.16

### File hashes

| Algorithm | Hash digest |  |
| --- | --- | --- |
| SHA256 | `38b952b9ab6f1fca79ff2f4f34f06a6d02cc6978300d8e046ed1ada8c6b3ef12` | Copy |
| MD5 | `789d97c6440946c6b604052701dc1437` | Copy |
| BLAKE2b-256 | `bec36a50952afaffe50b8cda65938eb2b3923ff18cbf7a9a42d7b66bdba76785` | Copy |

Hashes for colppy\_api-1.2.2-py3-none-any.whl

[See more details on using hashes here.](https://pip.pypa.io/en/stable/topics/secure-installs/#hash-checking-mode "External link")

![](https://pypi.org/static/images/white-cube.2351a86c.svg)

## Help

- [Installing packages](https://packaging.python.org/tutorials/installing-packages/ "External link")
- [Uploading packages](https://packaging.python.org/tutorials/packaging-projects/ "External link")
- [User guide](https://packaging.python.org/ "External link")
- [Project name retention](https://www.python.org/dev/peps/pep-0541/ "External link")
- [FAQs](https://pypi.org/help/)

## About PyPI

- [PyPI Blog](https://blog.pypi.org/ "External link")
- [Infrastructure dashboard](https://dtdg.co/pypi "External link")
- [Statistics](https://pypi.org/stats/)
- [Logos & trademarks](https://pypi.org/trademarks/)
- [Our sponsors](https://pypi.org/sponsors/)

## Contributing to PyPI

- [Bugs and feedback](https://pypi.org/help/#feedback)
- [Contribute on GitHub](https://github.com/pypi/warehouse "External link")
- [Translate PyPI](https://hosted.weblate.org/projects/pypa/warehouse/ "External link")
- [Sponsor PyPI](https://pypi.org/sponsors/)
- [Development credits](https://github.com/pypi/warehouse/graphs/contributors "External link")

## Using PyPI

- [Terms of Service](https://policies.python.org/pypi.org/Terms-of-Service/ "External link")
- [Report security issue](https://pypi.org/security/)
- [Code of conduct](https://policies.python.org/python.org/code-of-conduct/ "External link")
- [Privacy Notice](https://policies.python.org/pypi.org/Privacy-Notice/ "External link")
- [Acceptable Use Policy](https://policies.python.org/pypi.org/Acceptable-Use-Policy/ "External link")

* * *

Status: [all systems operational](https://status.python.org/ "External link")

Developed and maintained by the Python community, for the Python community.

[Donate today!](https://donate.pypi.org/)

"PyPI", "Python Package Index", and the blocks logos are registered [trademarks](https://pypi.org/trademarks/) of the [Python Software Foundation](https://www.python.org/psf-landing).


© 2026 [Python Software Foundation](https://www.python.org/psf-landing/ "External link")

[Site map](https://pypi.org/sitemap/)

Switch to desktop version

- English
- español
- français
- 日本語
- português (Brasil)
- українська
- Ελληνικά
- Deutsch
- 中文 (简体)
- 中文 (繁體)
- русский
- עברית
- Esperanto
- 한국어

Supported by

[![](https://pypi-camo.freetls.fastly.net/ed7074cadad1a06f56bc520ad9bd3e00d0704c5b/68747470733a2f2f73746f726167652e676f6f676c65617069732e636f6d2f707970692d6173736574732f73706f6e736f726c6f676f732f6177732d77686974652d6c6f676f2d7443615473387a432e706e67)AWS\\
Cloud computing and Security Sponsor](https://aws.amazon.com/) [![](https://pypi-camo.freetls.fastly.net/8855f7c063a3bdb5b0ce8d91bfc50cf851cc5c51/68747470733a2f2f73746f726167652e676f6f676c65617069732e636f6d2f707970692d6173736574732f73706f6e736f726c6f676f732f64617461646f672d77686974652d6c6f676f2d6668644c4e666c6f2e706e67)Datadog\\
Monitoring](https://www.datadoghq.com/) [![](https://pypi-camo.freetls.fastly.net/60f709d24f3e4d469f9adc77c65e2f5291a3d165/68747470733a2f2f73746f726167652e676f6f676c65617069732e636f6d2f707970692d6173736574732f73706f6e736f726c6f676f732f6465706f742d77686974652d6c6f676f2d7038506f476831302e706e67)Depot\\
Continuous Integration](https://depot.dev/) [![](https://pypi-camo.freetls.fastly.net/df6fe8829cbff2d7f668d98571df1fd011f36192/68747470733a2f2f73746f726167652e676f6f676c65617069732e636f6d2f707970692d6173736574732f73706f6e736f726c6f676f732f666173746c792d77686974652d6c6f676f2d65684d3077735f6f2e706e67)Fastly\\
CDN](https://www.fastly.com/) [![](https://pypi-camo.freetls.fastly.net/420cc8cf360bac879e24c923b2f50ba7d1314fb0/68747470733a2f2f73746f726167652e676f6f676c65617069732e636f6d2f707970692d6173736574732f73706f6e736f726c6f676f732f676f6f676c652d77686974652d6c6f676f2d616734424e3774332e706e67)Google\\
Download Analytics](https://careers.google.com/) [![](https://pypi-camo.freetls.fastly.net/d01053c02f3a626b73ffcb06b96367fdbbf9e230/68747470733a2f2f73746f726167652e676f6f676c65617069732e636f6d2f707970692d6173736574732f73706f6e736f726c6f676f732f70696e67646f6d2d77686974652d6c6f676f2d67355831547546362e706e67)Pingdom\\
Monitoring](https://www.pingdom.com/) [![](https://pypi-camo.freetls.fastly.net/67af7117035e2345bacb5a82e9aa8b5b3e70701d/68747470733a2f2f73746f726167652e676f6f676c65617069732e636f6d2f707970692d6173736574732f73706f6e736f726c6f676f732f73656e7472792d77686974652d6c6f676f2d4a2d6b64742d706e2e706e67)Sentry\\
Error logging](https://sentry.io/for/python/?utm_source=pypi&utm_medium=paid-community&utm_campaign=python-na-evergreen&utm_content=static-ad-pypi-sponsor-learnmore) [![](https://pypi-camo.freetls.fastly.net/b611884ff90435a0575dbab7d9b0d3e60f136466/68747470733a2f2f73746f726167652e676f6f676c65617069732e636f6d2f707970692d6173736574732f73706f6e736f726c6f676f732f737461747573706167652d77686974652d6c6f676f2d5467476c6a4a2d502e706e67)StatusPage\\
Status page](https://statuspage.io/)