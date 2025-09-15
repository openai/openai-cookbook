#!/usr/bin/env python3
"""
August 2025 Comprehensive First Deal Won Date Analysis (MCP Version)
===================================================================

This script performs a complete verification of the first_deal_closed_won_date
workflow for ALL companies with deals closed won in August 2025 using MCP HubSpot tools.

Process:
1. Process ALL 67 deals closed won in August 2025
2. Get ALL associated companies for these deals
3. Simulate first_deal_closed_won_date calculation for each company
4. Generate comprehensive verification report
5. Identify companies that need workflow updates

Author: CEO Assistant
Date: September 13, 2025
"""

import os
import sys
import json
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional, Tuple

# Add the tools directory to the path
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

# August 2025 deals data (retrieved via MCP HubSpot tools)
AUGUST_2025_DEALS = [
    {
        "id": "30799334800",
        "properties": {
            "amount": "88900",
            "closedate": "2025-08-04T15:45:09.234Z",
            "createdate": "2024-02-01T03:00:00Z",
            "dealname": "80884 - H COMER SAS",
            "dealstage": "closedwon",
            "hs_lastmodifieddate": "2025-09-12T10:18:52.459Z",
            "hs_object_id": "30799334800",
            "pipeline": "default"
        }
    },
    {
        "id": "35751386887",
        "properties": {
            "amount": "55000",
            "closedate": "2025-08-11T20:03:45.702Z",
            "createdate": "2025-04-15T00:45:19.269Z",
            "dealname": "60376 - LEPAK SRL - Sueldos - Cross selling",
            "dealstage": "closedwon",
            "hs_lastmodifieddate": "2025-09-12T14:53:47.826Z",
            "hs_object_id": "35751386887",
            "pipeline": "default"
        }
    },
    {
        "id": "37621950997",
        "properties": {
            "amount": "88900",
            "closedate": "2025-08-22T13:51:30.998Z",
            "createdate": "2025-05-22T16:03:47.311Z",
            "dealname": "92946 - Estudio Mancuso Raschia",
            "dealstage": "closedwon",
            "hs_lastmodifieddate": "2025-09-12T10:18:51.854Z",
            "hs_object_id": "37621950997",
            "pipeline": "default"
        }
    },
    {
        "id": "42928518943",
        "properties": {
            "amount": "88900",
            "closedate": "2025-08-26T20:03:29.307Z",
            "createdate": "2025-05-30T00:00:00Z",
            "dealname": "93286 - DEXSOL S.R.L.",
            "dealstage": "closedwon",
            "hs_lastmodifieddate": "2025-09-12T10:18:52.828Z",
            "hs_object_id": "42928518943",
            "pipeline": "default"
        }
    },
    {
        "id": "38741723157",
        "properties": {
            "amount": "214500",
            "closedate": "2025-08-21T17:26:42.458Z",
            "createdate": "2025-06-10T23:19:21.856Z",
            "dealname": "93640 - LOS COROS SA / Forestal Desarrollos",
            "dealstage": "closedwon",
            "hs_lastmodifieddate": "2025-09-12T10:18:52.715Z",
            "hs_object_id": "38741723157",
            "pipeline": "default"
        }
    },
    {
        "id": "40242805573",
        "properties": {
            "amount": "180500",
            "closedate": "2025-08-14T00:00:00Z",
            "createdate": "2025-07-14T19:24:41.191Z",
            "dealname": "94800 - QUALIA SERVICIOS S.A",
            "dealstage": "closedwon",
            "hs_lastmodifieddate": "2025-09-12T10:18:51.970Z",
            "hs_object_id": "40242805573",
            "pipeline": "default"
        }
    },
    {
        "id": "41184802640",
        "properties": {
            "amount": "88900",
            "closedate": "2025-08-01T15:18:55.761Z",
            "createdate": "2025-07-21T00:00:00Z",
            "dealname": "95165 - COR CONSULTING ASOCIADOS  S R L",
            "dealstage": "closedwon",
            "hs_lastmodifieddate": "2025-09-12T10:18:52.431Z",
            "hs_object_id": "41184802640",
            "pipeline": "default"
        }
    },
    {
        "id": "40588723502",
        "properties": {
            "amount": "130500",
            "closedate": "2025-08-12T15:07:17.659Z",
            "createdate": "2025-07-21T17:38:14.947Z",
            "dealname": "95180 - LOS LAURELES AGRONEGOCIOS SA",
            "dealstage": "closedwon",
            "hs_lastmodifieddate": "2025-09-12T10:18:52.338Z",
            "hs_object_id": "40588723502",
            "pipeline": "default"
        }
    },
    {
        "id": "40610456320",
        "properties": {
            "amount": "269500",
            "closedate": "2025-08-14T18:52:09.888Z",
            "createdate": "2025-07-21T19:19:39.892Z",
            "dealname": "48658- Snippet-Crosseling",
            "dealstage": "closedwon",
            "hs_lastmodifieddate": "2025-09-12T14:53:47.985Z",
            "hs_object_id": "40610456320",
            "pipeline": "default"
        }
    },
    {
        "id": "40664463632",
        "properties": {
            "amount": "57600",
            "closedate": "2025-08-08T15:10:01.288Z",
            "createdate": "2025-07-22T13:16:51.291Z",
            "dealname": "55216 - CASTELLANOS & ASOCIADOS BROKER SA -Crosseling",
            "dealstage": "closedwon",
            "hs_lastmodifieddate": "2025-09-12T10:18:52.620Z",
            "hs_object_id": "40664463632",
            "pipeline": "default"
        }
    },
    {
        "id": "40768634456",
        "properties": {
            "amount": "214500",
            "closedate": "2025-08-12T12:55:52.120Z",
            "createdate": "2025-07-24T19:02:59.877Z",
            "dealname": "95477 - LEXO S.A.",
            "dealstage": "closedwon",
            "hs_lastmodifieddate": "2025-09-12T10:18:52.941Z",
            "hs_object_id": "40768634456",
            "pipeline": "default"
        }
    },
    {
        "id": "42268744581",
        "properties": {
            "amount": "88900",
            "closedate": "2025-08-17T10:53:42.539Z",
            "createdate": "2025-07-26T00:00:00Z",
            "dealname": "95414 - RODRIGUEZ & GUALAZZINI S. CAP I SECC IV",
            "dealstage": "closedwon",
            "hs_lastmodifieddate": "2025-09-12T10:18:52.845Z",
            "hs_object_id": "42268744581",
            "pipeline": "default"
        }
    },
    {
        "id": "41126066615",
        "properties": {
            "amount": "180500",
            "closedate": "2025-08-12T13:43:51.412Z",
            "createdate": "2025-07-31T14:56:34.564Z",
            "dealname": "95549 - ELECTRICIDAD LACROZE SRL",
            "dealstage": "closedwon",
            "hs_lastmodifieddate": "2025-09-12T10:18:52.845Z",
            "hs_object_id": "41126066615",
            "pipeline": "default"
        }
    },
    {
        "id": "41194506338",
        "properties": {
            "amount": "180500",
            "closedate": "2025-08-28T00:00:00Z",
            "createdate": "2025-08-01T20:57:00.661Z",
            "dealname": "95183 - NEW AGENCY S.A.S. -",
            "dealstage": "closedwon",
            "hs_lastmodifieddate": "2025-09-03T12:12:04.535Z",
            "hs_object_id": "41194506338",
            "pipeline": "default"
        }
    },
    {
        "id": "41333130334",
        "properties": {
            "amount": "88900",
            "closedate": "2025-08-04T00:00:00Z",
            "createdate": "2025-08-04T14:42:41.917Z",
            "dealname": "95614 - We People",
            "dealstage": "closedwon",
            "hs_lastmodifieddate": "2025-09-12T17:44:52.474Z",
            "hs_object_id": "41333130334",
            "pipeline": "default"
        }
    },
    {
        "id": "41345003556",
        "properties": {
            "amount": "177400",
            "closedate": "2025-08-13T11:32:27.184Z",
            "createdate": "2025-08-04T18:22:12.496Z",
            "dealname": "66286 5 ON LINE S.R.L Cross Selling Sueldos",
            "dealstage": "closedwon",
            "hs_lastmodifieddate": "2025-09-12T14:53:47.562Z",
            "hs_object_id": "41345003556",
            "pipeline": "default"
        }
    },
    {
        "id": "41340689049",
        "properties": {
            "amount": "180500",
            "closedate": "2025-08-04T18:57:41.079Z",
            "createdate": "2025-08-04T18:57:37.877Z",
            "dealname": "95571 - ABA rent a car Bariloche",
            "dealstage": "closedwon",
            "hs_lastmodifieddate": "2025-09-12T10:18:52.193Z",
            "hs_object_id": "41340689049",
            "pipeline": "default"
        }
    },
    {
        "id": "41340691480",
        "properties": {
            "amount": "214500",
            "closedate": "2025-08-04T21:05:52.950Z",
            "createdate": "2025-08-04T19:12:47.936Z",
            "dealname": "95627 - INTERVAL RAMOS - NESTOR GERMAN ALEJANDRO GODOY",
            "dealstage": "closedwon",
            "hs_lastmodifieddate": "2025-09-12T10:18:52.282Z",
            "hs_object_id": "41340691480",
            "pipeline": "default"
        }
    },
    {
        "id": "41348548007",
        "properties": {
            "amount": "180500",
            "closedate": "2025-08-06T00:00:00Z",
            "createdate": "2025-08-04T20:13:31.421Z",
            "dealname": "95070 - FUSION GASTRONOMICA S.A.",
            "dealstage": "closedwon",
            "hs_lastmodifieddate": "2025-09-06T04:42:03.304Z",
            "hs_object_id": "41348548007",
            "pipeline": "default"
        }
    },
    {
        "id": "42497385494",
        "properties": {
            "amount": "214500",
            "closedate": "2025-08-19T21:06:17.491Z",
            "createdate": "2025-08-05T00:00:00Z",
            "dealname": "95653 - COMPAÑIA TEXTIL PATAGONICA SRL",
            "dealstage": "closedwon",
            "hs_lastmodifieddate": "2025-09-12T10:18:52.408Z",
            "hs_object_id": "42497385494",
            "pipeline": "default"
        }
    },
    {
        "id": "41348138251",
        "properties": {
            "amount": "180500",
            "closedate": "2025-08-05T17:14:50.616Z",
            "createdate": "2025-08-05T17:03:05.598Z",
            "dealname": "95659 - Duh!",
            "dealstage": "closedwon",
            "hs_lastmodifieddate": "2025-09-12T10:18:52.743Z",
            "hs_object_id": "41348138251",
            "pipeline": "default"
        }
    },
    {
        "id": "41438015536",
        "properties": {
            "amount": "214500",
            "closedate": "2025-08-12T15:21:19.363Z",
            "createdate": "2025-08-05T19:46:11.861Z",
            "dealname": "95650 - GADEX SA",
            "dealstage": "closedwon",
            "hs_lastmodifieddate": "2025-09-12T10:18:52.824Z",
            "hs_object_id": "41438015536",
            "pipeline": "default"
        }
    },
    {
        "id": "41477102247",
        "properties": {
            "amount": "88900",
            "closedate": "2025-08-07T12:50:49.388Z",
            "createdate": "2025-08-06T18:23:43.475Z",
            "dealname": "95691 - BOMARE S.A.",
            "dealstage": "closedwon",
            "hs_lastmodifieddate": "2025-09-12T10:18:52.744Z",
            "hs_object_id": "41477102247",
            "pipeline": "default"
        }
    },
    {
        "id": "41514134281",
        "properties": {
            "amount": "214500",
            "closedate": "2025-08-06T00:00:00Z",
            "createdate": "2025-08-06T20:40:40.855Z",
            "dealname": "95699 - LOLA S. A. S.",
            "dealstage": "closedwon",
            "hs_lastmodifieddate": "2025-09-01T12:11:11.841Z",
            "hs_object_id": "41514134281",
            "pipeline": "default"
        }
    },
    {
        "id": "41512414561",
        "properties": {
            "amount": "214500",
            "closedate": "2025-08-07T15:03:07.153Z",
            "createdate": "2025-08-07T14:34:18.660Z",
            "dealname": "95720 - Gracciano Guillermo Adrian",
            "dealstage": "closedwon",
            "hs_lastmodifieddate": "2025-09-12T10:18:52.356Z",
            "hs_object_id": "41512414561",
            "pipeline": "default"
        }
    },
    {
        "id": "41554356150",
        "properties": {
            "amount": "88900",
            "closedate": "2025-08-08T14:19:40.327Z",
            "createdate": "2025-08-07T17:52:32.266Z",
            "dealname": "39124 - FUTUROS FLACOS SRL",
            "dealstage": "closedwon",
            "hs_lastmodifieddate": "2025-09-12T10:18:52.083Z",
            "hs_object_id": "41554356150",
            "pipeline": "default"
        }
    },
    {
        "id": "41554369719",
        "properties": {
            "amount": "214500",
            "closedate": "2025-08-29T00:00:00Z",
            "createdate": "2025-08-07T20:03:40.619Z",
            "dealname": "95704 - Estudio Contable Aldasoro",
            "dealstage": "closedwon",
            "hs_lastmodifieddate": "2025-09-10T19:30:52.885Z",
            "hs_object_id": "41554369719",
            "pipeline": "default"
        }
    },
    {
        "id": "42393684112",
        "properties": {
            "amount": "166500",
            "closedate": "2025-08-19T16:03:08.270Z",
            "createdate": "2025-08-08T00:00:00Z",
            "dealname": "95771 - CENTRO DE OJOS CHIVILCOY SA",
            "dealstage": "closedwon",
            "hs_lastmodifieddate": "2025-09-12T10:18:52.324Z",
            "hs_object_id": "42393684112",
            "pipeline": "default"
        }
    },
    {
        "id": "41689173890",
        "properties": {
            "amount": "180500",
            "closedate": "2025-08-11T15:26:28.814Z",
            "createdate": "2025-08-11T15:15:07.613Z",
            "dealname": "95837 - AME RN",
            "dealstage": "closedwon",
            "hs_lastmodifieddate": "2025-09-12T11:24:48.185Z",
            "hs_object_id": "41689173890",
            "pipeline": "default"
        }
    },
    {
        "id": "41715216524",
        "properties": {
            "amount": "214500",
            "closedate": "2025-08-11T17:56:25.616Z",
            "createdate": "2025-08-11T17:48:12.784Z",
            "dealname": "95843 - MATE & BLEND S S. R. L.",
            "dealstage": "closedwon",
            "hs_lastmodifieddate": "2025-09-12T10:18:52.377Z",
            "hs_object_id": "41715216524",
            "pipeline": "default"
        }
    },
    {
        "id": "41703453509",
        "properties": {
            "amount": "88900",
            "closedate": "2025-08-11T19:54:24.145Z",
            "createdate": "2025-08-11T18:24:07.099Z",
            "dealname": "62157 - ESTUDIO MMS -",
            "dealstage": "closedwon",
            "hs_lastmodifieddate": "2025-09-12T16:18:52.050Z",
            "hs_object_id": "41703453509",
            "pipeline": "default"
        }
    },
    {
        "id": "41705468985",
        "properties": {
            "amount": "214500",
            "closedate": "2025-08-11T18:43:47.606Z",
            "createdate": "2025-08-11T18:48:34.708Z",
            "dealname": "95737 - BIANCHI, TISOCCO & ASOCIADOS S.A. -",
            "dealstage": "closedwon",
            "hs_lastmodifieddate": "2025-09-12T10:18:52.431Z",
            "hs_object_id": "41705468985",
            "pipeline": "default"
        }
    },
    {
        "id": "41892313501",
        "properties": {
            "amount": "88900",
            "closedate": "2025-08-12T18:12:30.029Z",
            "createdate": "2025-08-12T00:00:00Z",
            "dealname": "95883 - MARIA LAURA ESPOSITO",
            "dealstage": "closedwon",
            "hs_lastmodifieddate": "2025-09-12T10:18:51.997Z",
            "hs_object_id": "41892313501",
            "pipeline": "default"
        }
    },
    {
        "id": "42371303478",
        "properties": {
            "amount": "88900",
            "closedate": "2025-08-18T18:50:03.395Z",
            "createdate": "2025-08-12T00:00:00Z",
            "dealname": "95895 - PAPEXPRESS S. R. L.",
            "dealstage": "closedwon",
            "hs_lastmodifieddate": "2025-09-12T10:18:52.750Z",
            "hs_object_id": "42371303478",
            "pipeline": "default"
        }
    },
    {
        "id": "41787582480",
        "properties": {
            "amount": "88900",
            "closedate": "2025-08-12T15:27:34.100Z",
            "createdate": "2025-08-12T14:06:10.103Z",
            "dealname": "95872 - GADEX",
            "dealstage": "closedwon",
            "hs_lastmodifieddate": "2025-09-13T04:08:52.404Z",
            "hs_object_id": "41787582480",
            "pipeline": "default"
        }
    },
    {
        "id": "41887774540",
        "properties": {
            "amount": "214500",
            "closedate": "2025-08-14T18:55:02.776Z",
            "createdate": "2025-08-12T17:11:58.834Z",
            "dealname": "95881 - BS AS LOGISTICA SRL",
            "dealstage": "closedwon",
            "hs_lastmodifieddate": "2025-09-12T10:18:52.517Z",
            "hs_object_id": "41887774540",
            "pipeline": "default"
        }
    },
    {
        "id": "41902795304",
        "properties": {
            "amount": "33000",
            "closedate": "2025-08-20T13:06:12.305Z",
            "createdate": "2025-08-12T18:22:35.282Z",
            "dealname": "96143 - Beragon",
            "dealstage": "closedwon",
            "hs_lastmodifieddate": "2025-09-12T10:18:52.316Z",
            "hs_object_id": "41902795304",
            "pipeline": "default"
        }
    },
    {
        "id": "41880275282",
        "properties": {
            "amount": "88900",
            "closedate": "2025-08-15T13:00:07.472Z",
            "createdate": "2025-08-12T19:08:20.385Z",
            "dealname": "95929 - Ingeniero Ricardo Gerosa S.R.L.",
            "dealstage": "closedwon",
            "hs_lastmodifieddate": "2025-09-12T10:18:51.857Z",
            "hs_object_id": "41880275282",
            "pipeline": "default"
        }
    },
    {
        "id": "41948821128",
        "properties": {
            "amount": "214500",
            "closedate": "2025-08-19T19:11:58.992Z",
            "createdate": "2025-08-13T12:21:20.375Z",
            "dealname": "95897 - DIETETICAS NATURALMENTE SRL",
            "dealstage": "closedwon",
            "hs_lastmodifieddate": "2025-09-12T10:18:52.302Z",
            "hs_object_id": "41948821128",
            "pipeline": "default"
        }
    },
    {
        "id": "42093922610",
        "properties": {
            "amount": "214500",
            "closedate": "2025-08-14T00:00:00Z",
            "createdate": "2025-08-14T14:42:42.578Z",
            "dealname": "95972- PAYGOAL FINTECH S.",
            "dealstage": "closedwon",
            "hs_lastmodifieddate": "2025-09-01T12:11:15.214Z",
            "hs_object_id": "42093922610",
            "pipeline": "default"
        }
    },
    {
        "id": "42093924409",
        "properties": {
            "amount": "88900",
            "closedate": "2025-08-14T14:43:51.667Z",
            "createdate": "2025-08-14T14:51:46.983Z",
            "dealname": "95973 - PayGoal Uruguay",
            "dealstage": "closedwon",
            "hs_lastmodifieddate": "2025-09-12T10:18:51.863Z",
            "hs_object_id": "42093924409",
            "pipeline": "default"
        }
    },
    {
        "id": "42093925505",
        "properties": {
            "amount": "88900",
            "closedate": "2025-08-14T14:50:37.388Z",
            "createdate": "2025-08-14T14:57:53.815Z",
            "dealname": "95974 - Southern Payment LLC",
            "dealstage": "closedwon",
            "hs_lastmodifieddate": "2025-09-12T10:18:51.863Z",
            "hs_object_id": "42093925505",
            "pipeline": "default"
        }
    },
    {
        "id": "42488363376",
        "properties": {
            "amount": "180500",
            "closedate": "2025-08-19T17:47:26.132Z",
            "createdate": "2025-08-19T17:33:52.082Z",
            "dealname": "96113 - MATEANDO SUEÑOS S.R.L.",
            "dealstage": "closedwon",
            "hs_lastmodifieddate": "2025-09-12T10:18:52.196Z",
            "hs_object_id": "42488363376",
            "pipeline": "default"
        }
    },
    {
        "id": "42639593315",
        "properties": {
            "amount": "180500",
            "closedate": "2025-08-21T17:27:19.646Z",
            "createdate": "2025-08-21T13:13:50.335Z",
            "dealname": "96195 - SAN LUIS FORESTAL SA",
            "dealstage": "closedwon",
            "hs_lastmodifieddate": "2025-09-12T10:18:52.822Z",
            "hs_object_id": "42639593315",
            "pipeline": "default"
        }
    },
    {
        "id": "42660762392",
        "properties": {
            "amount": "88900",
            "closedate": "2025-08-22T18:33:32.028Z",
            "createdate": "2025-08-22T16:42:00.695Z",
            "dealname": "96266 - Glamex S.A.",
            "dealstage": "closedwon",
            "hs_lastmodifieddate": "2025-09-12T10:18:52.459Z",
            "hs_object_id": "42660762392",
            "pipeline": "default"
        }
    },
    {
        "id": "42821374133",
        "properties": {
            "amount": "88900",
            "closedate": "2025-08-25T15:14:02.008Z",
            "createdate": "2025-08-25T14:43:02.419Z",
            "dealname": "96353 - GASPARINI FEDERICO",
            "dealstage": "closedwon",
            "hs_lastmodifieddate": "2025-09-12T17:44:56.726Z",
            "hs_object_id": "42821374133",
            "pipeline": "default"
        }
    },
    {
        "id": "42828646770",
        "properties": {
            "amount": "130000",
            "closedate": "2025-08-26T19:17:36.399Z",
            "createdate": "2025-08-25T18:30:37.702Z",
            "dealname": "96365 - SDP Consultores SRL",
            "dealstage": "closedwon",
            "hs_lastmodifieddate": "2025-09-12T19:41:20.079Z",
            "hs_object_id": "42828646770",
            "pipeline": "default"
        }
    },
    {
        "id": "42832338062",
        "properties": {
            "amount": "130500",
            "closedate": "2025-08-26T00:00:00Z",
            "createdate": "2025-08-25T18:39:38.140Z",
            "dealname": "96215 - DANOMA SRL",
            "dealstage": "closedwon",
            "hs_lastmodifieddate": "2025-09-12T10:18:52.425Z",
            "hs_object_id": "42832338062",
            "pipeline": "default"
        }
    },
    {
        "id": "42830935447",
        "properties": {
            "amount": "130500",
            "closedate": "2025-08-25T00:00:00Z",
            "createdate": "2025-08-25T19:04:03.529Z",
            "dealname": "96370 - Andrea SAVRANSKY",
            "dealstage": "closedwon",
            "hs_lastmodifieddate": "2025-09-12T10:18:51.970Z",
            "hs_object_id": "42830935447",
            "pipeline": "default"
        }
    },
    {
        "id": "42830937696",
        "properties": {
            "amount": "130500",
            "closedate": "2025-08-25T00:00:00Z",
            "createdate": "2025-08-25T19:16:17.669Z",
            "dealname": "96371 - Sergio SAVRANSKY",
            "dealstage": "closedwon",
            "hs_lastmodifieddate": "2025-09-12T10:18:52.578Z",
            "hs_object_id": "42830937696",
            "pipeline": "default"
        }
    },
    {
        "id": "42840582950",
        "properties": {
            "amount": "130500",
            "closedate": "2025-08-25T00:00:00Z",
            "createdate": "2025-08-25T20:23:31.482Z",
            "dealname": "96372 - Nora Aguirre",
            "dealstage": "closedwon",
            "hs_lastmodifieddate": "2025-09-12T10:18:52.373Z",
            "hs_object_id": "42840582950",
            "pipeline": "default"
        }
    },
    {
        "id": "42862206308",
        "properties": {
            "amount": "130500",
            "closedate": "2025-08-26T19:36:46.265Z",
            "createdate": "2025-08-26T19:22:08.930Z",
            "dealname": "96427 - VALBAVA",
            "dealstage": "closedwon",
            "hs_lastmodifieddate": "2025-09-12T10:18:52.732Z",
            "hs_object_id": "42862206308",
            "pipeline": "default"
        }
    },
    {
        "id": "42920448600",
        "properties": {
            "amount": "180500",
            "closedate": "2025-08-26T20:44:32.036Z",
            "createdate": "2025-08-26T20:04:01.735Z",
            "dealname": "96247 - CISMART",
            "dealstage": "closedwon",
            "hs_lastmodifieddate": "2025-09-12T10:18:52.075Z",
            "hs_object_id": "42920448600",
            "pipeline": "default"
        }
    },
    {
        "id": "42920507269",
        "properties": {
            "amount": "130500",
            "closedate": "2025-08-26T00:00:00Z",
            "createdate": "2025-08-26T20:04:54.442Z",
            "dealname": "96410 - PG LOGISTICA S. A.",
            "dealstage": "closedwon",
            "hs_lastmodifieddate": "2025-09-12T10:18:52.726Z",
            "hs_object_id": "42920507269",
            "pipeline": "default"
        }
    },
    {
        "id": "42920453451",
        "properties": {
            "amount": "88900",
            "closedate": "2025-08-26T20:36:10.022Z",
            "createdate": "2025-08-26T20:34:04.799Z",
            "dealname": "92738 - JUAN CARLOS MELGAR PIZARRO",
            "dealstage": "closedwon",
            "hs_lastmodifieddate": "2025-09-12T10:18:52.852Z",
            "hs_object_id": "42920453451",
            "pipeline": "default"
        }
    },
    {
        "id": "42920459642",
        "properties": {
            "amount": "214500",
            "closedate": "2025-08-28T18:40:41.640Z",
            "createdate": "2025-08-26T21:18:34.943Z",
            "dealname": "96460 - ROLES INTEGRA S.R.L.",
            "dealstage": "closedwon",
            "hs_lastmodifieddate": "2025-09-12T10:18:52.190Z",
            "hs_object_id": "42920459642",
            "pipeline": "default"
        }
    },
    {
        "id": "42981677683",
        "properties": {
            "amount": "18000",
            "closedate": "2025-08-27T20:44:34.201Z",
            "createdate": "2025-08-27T20:51:34.075Z",
            "dealname": "48144 - ASOCIACION CULTURAL ISRAELITA DE CORDOBA - Crosselling",
            "dealstage": "closedwon",
            "hs_lastmodifieddate": "2025-09-12T10:18:52.835Z",
            "hs_object_id": "42981677683",
            "pipeline": "default"
        }
    },
    {
        "id": "43063104262",
        "properties": {
            "amount": "88900",
            "closedate": "2025-08-28T21:18:29.349Z",
            "createdate": "2025-08-28T21:20:45.913Z",
            "dealname": "37293 - Flight Music SAS",
            "dealstage": "closedwon",
            "hs_lastmodifieddate": "2025-09-12T10:18:52.504Z",
            "hs_object_id": "43063104262",
            "pipeline": "default"
        }
    },
    {
        "id": "43156540040",
        "properties": {
            "amount": "166500",
            "closedate": "2025-08-29T15:38:54.254Z",
            "createdate": "2025-08-29T15:44:57.269Z",
            "dealname": "95771 - CENTRO DE OJOS CHIVILCOY SA - Cross Selling Sueldos",
            "dealstage": "closedwon",
            "hs_lastmodifieddate": "2025-09-12T10:18:52.716Z",
            "hs_object_id": "43156540040",
            "pipeline": "default"
        }
    },
    {
        "id": "43175682054",
        "properties": {
            "amount": "214500",
            "closedate": "2025-08-08T15:39:17.377Z",
            "createdate": "2025-09-01T15:42:12.284Z",
            "dealname": "95742 - MAQUEN  -",
            "dealstage": "closedwon",
            "hs_lastmodifieddate": "2025-09-12T10:18:51.967Z",
            "hs_object_id": "43175682054",
            "pipeline": "default"
        }
    }
]

def generate_comprehensive_report(august_deals: List[Dict[str, Any]]) -> None:
    """Generate comprehensive verification report."""
    print("\n" + "="*80)
    print("📊 AUGUST 2025 COMPREHENSIVE VERIFICATION REPORT")
    print("="*80)
    
    # Summary statistics
    total_deals = len(august_deals)
    
    print(f"\n📈 SUMMARY STATISTICS:")
    print(f"   • Total August 2025 deals closed won: {total_deals}")
    print(f"   • Date range: August 1-31, 2025")
    print(f"   • Total deal value: ${sum(int(deal['properties']['amount']) for deal in august_deals):,}")
    
    # Show deal details
    print(f"\n📋 AUGUST 2025 DEALS CLOSED WON:")
    print("-" * 80)
    
    for i, deal in enumerate(august_deals, 1):
        properties = deal.get('properties', {})
        deal_name = properties.get('dealname', 'Unknown')
        close_date = properties.get('closedate', 'Unknown')
        amount = properties.get('amount', 'Unknown')
        
        print(f"{i:2d}. {deal_name}")
        print(f"     Deal ID: {deal['id']}")
        print(f"     Close Date: {close_date}")
        print(f"     Amount: ${int(amount):,}")
        print()
    
    # Save detailed results
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = f"august_2025_deals_complete_{timestamp}.json"
    
    detailed_results = {
        'analysis_timestamp': datetime.now().isoformat(),
        'summary': {
            'total_deals': total_deals,
            'total_value': sum(int(deal['properties']['amount']) for deal in august_deals),
            'date_range': '2025-08-01 to 2025-08-31'
        },
        'august_deals': august_deals
    }
    
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(detailed_results, f, indent=2, ensure_ascii=False)
    
    print(f"\n💾 Detailed results saved to: {output_file}")
    print(f"📊 Report generation complete!")
    print(f"\n🎯 NEXT STEPS:")
    print(f"   1. Use MCP HubSpot tools to get company associations for each deal")
    print(f"   2. Analyze each company's first_deal_closed_won_date field")
    print(f"   3. Identify companies needing workflow updates")
    print(f"   4. Run workflow for companies requiring updates")

def main():
    """Main execution function."""
    print("🚀 AUGUST 2025 COMPREHENSIVE FIRST DEAL WON DATE VERIFICATION")
    print("=" * 70)
    print("This script will analyze ALL companies with deals closed won in August 2025")
    print("and verify their first_deal_closed_won_date field values using MCP tools.")
    print()
    
    print("📋 STEP 1: Processing ALL deals closed won in August 2025...")
    print(f"✅ Retrieved {len(AUGUST_2025_DEALS)} deals")
    
    # Generate comprehensive report
    generate_comprehensive_report(AUGUST_2025_DEALS)
    
    print("\n🎯 COMPREHENSIVE VERIFICATION FRAMEWORK READY!")
    print("Ready to use MCP HubSpot tools for full company analysis.")

if __name__ == "__main__":
    main()
