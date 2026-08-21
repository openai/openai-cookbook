# AUMARA Nominalia domain routing probe

- UTC: 2026-08-15T13:59:37Z
- EL CID A: `213.158.93.19`
- AUMARA apex A: `81.88.48.71`
- AUMARA www A: `aumara.me.,81.88.48.71`
- AUMARA www CNAME: `aumara.me.`
- AUMARA NS: `dns1.nominalia.com.,dns2.nominalia.com.`
- Nominalia FTP host A: `213.158.92.149`
- FTP /www/aumara access: **yes**

## Public HTTP
- http://aumara.me/: `200|http://aumara.me/|81.88.48.71|text/html|924`
- https://aumara.me/: `503|https://aumara.me/|81.88.48.71|text/html|537`
- http://www.aumara.me/: `200|http://www.aumara.me/|81.88.48.71|text/html|924`
- https://www.aumara.me/: `503|https://www.aumara.me/|81.88.48.71|text/html|537`
- https://elcidspain.com/: `200|https://elcidspain.com/|213.158.93.19|text/html; charset=UTF-8|28107`

## Direct vhost test against EL CID production IP
- HTTP aumara.me -> EL CID IP: `200|213.158.93.19|text/html|52`; AUMARA marker: **no**
- HTTPS aumara.me -> EL CID IP: `200|213.158.93.19|text/html|52`; AUMARA marker: **no**
