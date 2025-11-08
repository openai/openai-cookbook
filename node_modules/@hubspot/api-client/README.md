# hubspot-api-nodejs

NodeJS v3 [HubSpot API](https://developers.hubspot.com/docs/api/overview) SDK(Client) files

## Sample apps

Please, take a look at our [Sample apps](https://github.com/HubSpot/sample-apps-list)

## Available SDK methods reference

[Available SDK methods reference](https://github.hubspot.com/hubspot-api-nodejs/)

## Installing

```shell
npm install @hubspot/api-client
```

## Instantiate client

```javascript
const hubspot = require('@hubspot/api-client')
const hubspotClient = new hubspot.Client({ accessToken: YOUR_ACCESS_TOKEN })
```

> [!NOTE]
> Please note that all code examples are written in JavaScript. Some of them won’t work in Typescript without changes.

For ES modules

```javascript
import { Client } from "@hubspot/api-client";
const hubspotClient = new Client({ accessToken: YOUR_ACCESS_TOKEN });
```

You'll need to create a [private app](https://developers.hubspot.com/docs/apps/legacy-apps/private-apps/overview) to get your access token or you can obtain [OAuth2 access token](https://developers.hubspot.com/docs/api-reference/auth-oauth-v1/guide).

You can provide developer API key. There is no need to create separate client instances for using endpoints with API key and Developer API key support.

```javascript
const hubspotClient = new hubspot.Client({ developerApiKey: YOUR_DEVELOPER_API_KEY })
```

```javascript
const hubspotClient = new hubspot.Client({ accessToken: YOUR_ACCESS_TOKEN, developerApiKey: YOUR_DEVELOPER_API_KEY })
```

To change the base path:

```javascript
const hubspotClient = new hubspot.Client({ accessToken: YOUR_ACCESS_TOKEN, basePath: 'https://some-url' })
```

To add custom headers to all request:

```javascript
const hubspotClient = new hubspot.Client({
    accessToken: YOUR_ACCESS_TOKEN,
    defaultHeaders: { 'My-header': 'test-example' },
})
```

If you're an app developer, you can also instantiate a client and obtain a new accessToken with your app
details and a refresh_token:

```javascript
hubspotClient.oauth.tokensApi
    .create('refresh_token', undefined, undefined, YOUR_CLIENT_ID, YOUR_CLIENT_SECRET, YOUR_REFRESH_TOKEN)
    .then((results) => {
        console.log(results)

        // this assigns the accessToken to the client, so your client is ready
        // to use
        hubspotClient.setAccessToken(results.accessToken)

        return hubspotClient.crm.companies.basicApi.getPage()
    })
```

### Rate limiting

[Bottleneck](https://github.com/SGrondin/bottleneck) is used for rate limiting. To turn on/off rate limiting use `limiterOptions` option on Client instance creation. Bottleneck options can be found [here](https://github.com/SGrondin/bottleneck#constructor).
Please note that Apps using OAuth are only subject to a limit of 100 requests every 10 seconds. Limits related to the API Add-on don't apply.

```javascript
const hubspotClient = new hubspot.Client({
    accessToken: YOUR_ACCESS_TOKEN,
    limiterOptions: DEFAULT_LIMITER_OPTIONS,
})
```

Default settings for the limiter are:

```javascript
const DEFAULT_LIMITER_OPTIONS = {
    minTime: 1000 / 9,
    maxConcurrent: 6,
    id: 'hubspot-client-limiter',
}
```

Search settings for the limiter are:

```javascript
const SEARCH_LIMITER_OPTIONS = {
    minTime: 550,
    maxConcurrent: 3,
    id: 'search-hubspot-client-limiter',
}
```

### Retry mechanism

It's possible to turn on retry for failed requests with statuses 429 or 5xx. To turn on/off configurable retries use `numberOfApiCallRetries` option on Client instance creation. `numberOfApiCallRetries` can be set to a number from 0 - 6. If `numberOfApiCallRetries` is set to a number greater than 0 it means that if any API Call receives ISE5xx this call will be retried after a delay 200 * retryNumber ms and if 429 (Rate limit is exceeded) is returned for "TEN_SECONDLY_ROLLING" the call will be retried after a delay 10 sec. Number of retries will not exceed `numberOfApiCallRetries` value.

```javascript
const hubspotClient = new hubspot.Client({
    accessToken: YOUR_ACCESS_TOKEN,
    numberOfApiCallRetries: 3,
})
```

## Usage

All methods return a [promise]. The success includes the serialized to JSON body and response objects. Use the API method via:

```javascript
hubspotClient.crm.contacts.basicApi
    .getPage(limit, after, properties, propertiesWithHistory, associations, archived)
    .then((results) => {
        console.log(results)
    })
    .catch((err) => {
        console.error(err)
    })
```

[promise]: https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Promise

### {EXAMPLE} Create Contact, Company and associate created objects

```javascript
const contactObj = {
    properties: {
        firstname: yourValue,
        lastname: yourValue,
    },
}
const companyObj = {
    properties: {
        domain: yourValue,
        name: yourValue,
    },
}

const createContactResponse = await hubspotClient.crm.contacts.basicApi.create(contactObj)
const createCompanyResponse = await hubspotClient.crm.companies.basicApi.create(companyObj)
await hubspotClient.crm.associations.v4.basicApi.create(
    'companies',
    createCompanyResponse.id,
    'contacts',
    createContactResponse.id,
    [
        {
              "associationCategory": "HUBSPOT_DEFINED",
              "associationTypeId": AssociationTypes.companyToContact
              // AssociationTypes contains the most popular HubSpot defined association types
        }
    ]
)
```

### {EXAMPLE} Get associated Companies by Contact

```javascript
const companies = await hubspotClient.crm.associations.v4.basicApi.getPage(
    'contact',
    hubspotContactId,
    'company',
    after,
    pageSize,
  );
```

### {EXAMPLE} Update multiple objects in batch mode

```javascript
const dealObj = {
    id: yourId,
    properties: {
        amount: yourValue,
    },
}

const dealObj2 = {
    id: yourId,
    properties: {
        amount: yourValue,
    },
}

await hubspotClient.crm.deals.batchApi.update({ inputs: [dealObj, dealObj2] })
```

### {EXAMPLE} Import Contacts

```javascript
const fs = require('fs')

const fileName = 'test.csv'

const file = {
    data: fs.createReadStream(fileName),
    name: fileName,
};

const importRequest = {
    name: 'import(' + fileName + ')',
    files: [
        {
            fileName: fileName,
            fileImportPage: {
                hasHeader: true,
                columnMappings: [
                    {
                        columnName: 'First Name',
                        propertyName: 'firstname',
                        columnObjectType: 'CONTACT',
                    },
                    {
                        columnName: 'Email',
                        propertyName: 'email',
                        columnObjectType: 'CONTACT',
                    },
                ],
            },
        },
    ],
}

const response = await  hubspotClient.crm.imports.coreApi.create(file, JSON.stringify(importRequest));

console.log(response)
```

### CRM Search

Only 3 `FilterGroups` with max 3 `Filters` are supported.

Despite `sorts` is an array, however, currently, only one sort parameter is supported.

In JS `sorts` it's possible to set as:

1. < propertyName > - returned results will be sorted by provided property name in 'ASCENDING' order. e.g: `'hs_object_id'``
2. < direction > - returned results will be sorted by provided property name and sort direction. e.g: `{ propertyName: 'hs_object_id', direction: 'ASCENDING' }` or `{ propertyName: 'hs_object_id', direction: 'DESCENDING' }`

In TS `sorts` it's possible to set as:

1. < propertyName > - returned results will be sorted by provided property name in 'ASCENDING' order. e.g: `['hs_object_id']`
2. < direction > - use `["-createdate"]` to sort in desc and sorts: `["createdate"]` in asc order.

`after` for initial search should be set as 0

### {EXAMPLE} Search CRM Contacts

Example for JS:

```javascript
const publicObjectSearchRequest = {
    filterGroups: [
    {
        filters: [
        {
            propertyName: 'createdate',
            operator: 'GTE',
            value: `${Date.now() - 30 * 60000}`
        }
        ]
    }
    ],
    sorts: [{ propertyName: 'createdate', direction: 'DESCENDING' }],
    properties: ['createdate', 'firstname', 'lastname'],
    limit: 100,
    after: 0,
}

const response = await hubspotClient.crm.contacts.searchApi.doSearch(publicObjectSearchRequest)

console.log(response)
```

Example for TS:

```Typescript
const objectSearchRequest: PublicObjectSearchRequest = {
    filterGroups: [
        {
            filters: [
                {
                propertyName: "createdate",
                operator: "GTE",
                value: "1615709177000",
                },
            ],
        },
    ],
    sorts: ["-createdate"],
    properties: ["email", "createdate"],
    limit: 100,
    after: '0',
};

const response = await hubspotClient.crm.contacts.searchApi.doSearch(objectSearchRequest);

console.log(response)
```

### Get all

getAll method is available for all major objects (Companies, Contacts, Deals, LineItems, Products, Quotes & Tickets) and works like

```javascript
const allContacts = await hubspotClient.crm.contacts.getAll()
```

> [!NOTE]
> Please note that pagination is used under the hood to get all results.

### Upload a file (via the SDK)

```javascript
const response = await hubspotClient.files.filesApi.upload(
    {
        data: fs.createReadStream('./photo.jpg'),
        name: 'photo.jpg'
    },
    undefined,
    '/folder',
    'photo.jpg',
    undefined,
    JSON.stringify({
        access: 'PRIVATE',
        overwrite: false,
        duplicateValidationStrategy: 'NONE',
        duplicateValidationScope: 'ENTIRE_PORTAL',
    })
)

console.log(response)
```

### OAuth

#### Obtain your authorization url

```javascript
const clientId = 'your_client_id'
const redirectUri = 'take_me_to_the_ballpark'
const scope = 'some scopes'
const uri = hubspotClient.oauth.getAuthorizationUrl(clientId, redirectUri, scope)
```

#### Obtain an access token from an authorization_code

```javascript
return hubspotClient.oauth.tokensApi.create(
        'authorization_code',
        code, // the code you received from the oauth flow
        YOUR_REDIRECT_URI,
        YOUR_CLIENT_ID,
        YOUR_CLIENT_SECRET,
    ).then(...)
```

### CMS

#### Get audit logs

```javascript
const response = await hubspotClient.cms.auditLogs.auditLogsApi.getPage()
```

## Not wrapped endpoint(s)

It is possible to access the hubspot request method directly,
it could be handy if client doesn't have implementation for some endpoint yet.
Exposed request method benefits by having all configured client params.

```javascript
hubspotClient.apiRequest({
    method: 'PUT',
    path: '/some/api/not/wrapped/yet',
    body: { key: 'value' },
})
```

### Get contacts

```javascript
const response = await hubspotClient.apiRequest({
    path: '/crm/v3/objects/contacts',
})
const json = await response.json()
console.log(json)
```

### Upload a file

```javascript
const formData = new FormData();
const options = {
// some options
};
formData.append("folderPath", '/');
formData.append("options", JSON.stringify(options));
formData.append("file", fs.createReadStream('file path'));

const response = await hubspotClient.apiRequest({
    method: 'POST',
    path: '/filemanager/api/v3/files/upload',
    body: formData,
    defaultJson: false
});

console.log(response);
```

## Reserved words

The SDK has reserved words(e.g. `from`, `in`, `delete`). [Full list of reserved words.](https://openapi-generator.tech/docs/generators/typescript#reserved-words)
When you face with a reserved word you have to add `_` before the word(e.g. `_from`, `_in`, `_delete`).

```javascript
const BatchInputPublicAssociation = {
    inputs: [
        {
            _from: {
                id : 'contactID'
            },
            to: {
                id: 'companyID'
            },
            type: 'contact_to_company'
        }
    ]
};

const response = await hubspotClient.crm.associations.batchApi.create(
    'contacts',
    'companies',
    BatchInputPublicAssociation
);
```

## Typescript

You may use this library in your Typescript project via:

```typescript
import * as hubspot from '@hubspot/api-client'
const hubspotClient = new hubspot.Client({ accessToken: YOUR_ACCESS_TOKEN , developerApiKey: YOUR_DEVELOPER_API_KEY })
```

## License

Apache 2.0

## Contributing

Install project dependencies with

```bash
npm install
```

You can run the tests by executing:

```bash
npm run test
```

You can check the TypeScript code by running:

```bash
npm run lint
```

If there is a linting error based on formatting, you can run the command below to auto-correct the formatting:

```bash
npm run prettier:write
```
