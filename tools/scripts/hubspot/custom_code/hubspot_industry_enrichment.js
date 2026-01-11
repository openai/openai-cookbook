// =============================================================================
// HubSpot Custom Code - Industry Enrichment with LLM Classification
// =============================================================================
// source: hubspot_industry_enrichment.js
// Hubspot workflow: https://app.hubspot.com/workflows/19877595/platform/flow/1693911922/edit
// VERSION: 1.0.0
// LAST UPDATED: 2025-01-09
// PURPOSE: 
// Auto-populates industria field and Type field for companies using:
// 1. LLM-based classification from ARCA activity text (primary method)
// 2. Keyword-based classification from website content (fallback)
// 3. Company name analysis (final fallback)
//
// FEATURES:
// ✅ LLM CLASSIFICATION: Uses OpenAI API to classify industry from ARCA activity
// ✅ CUIT SEARCH: Searches dateas.com for company activity using CUIT
// ✅ WEBSITE SCRAPING: Analyzes website content for industry keywords
// ✅ DOMAIN SEARCH: Finds company domain from company name
// ✅ TYPE INFERENCE: Auto-populates Type field based on industria
// ✅ ACTIVITY SAVING: Saves cleaned ARCA activity to HubSpot field
//
// ENVIRONMENT VARIABLES REQUIRED:
// - ColppyCRMAutomations: HubSpot API token
// - OPENAI_API_KEY: OpenAI API key for LLM classification (optional - falls back to keyword matching if not set)
// - SlackWebhookUrl: Slack webhook URL for notifications (optional)

const hubspot = require('@hubspot/api-client');

// Load https module for fallback when fetch is not available
// In HubSpot custom code, require() must be at top level (cannot be in try-catch)
// https is a Node.js built-in module and should be available in HubSpot environment
const httpsModule = require('https');

/**
 * Map English enum values to Spanish industria field values
 */
function mapToIndustriaField(englishEnum) {
  const mapping = {
    'INFORMATION_TECHNOLOGY_AND_SERVICES': 'Desarrollo venta integración de software',
    'MANUFACTURING': 'Fabricación, Manufactura, Metalúrgica',
    'LOGISTICS_AND_SUPPLY_CHAIN': 'Logística, almacenamiento, transporte',
    'AGRICULTURE': 'Agricultura, ganadería, pesca',
    'FOOD_AND_BEVERAGE': 'Alimentos y bebidas',
    'CONSTRUCTION': 'Arquitectura, ingeniería, construcción',
    'RETAIL': 'Bazar en general',
    'PROFESSIONAL_SERVICES': 'Servicios de consultoría',
    'HEALTHCARE': 'Medicina, farmacéutica, salud, higiene',
    'EDUCATION': 'Educación en general',
    'FINANCIAL_SERVICES': 'Banca, finanzas, seguros',
    'LEGAL_SERVICES': 'Contabilidad, impuestos, legales',
    'MARKETING_AND_ADVERTISING': 'Marketing y publicidad',
    'HOSPITALITY': 'Hotelería y turismo',
    'AUTOMOTIVE': 'Automóviles, autopartes, automotriz',
    'ENERGY': 'Electrónica, electricidad, energía',
    'TEXTILES': 'Industria textil, moda, indumentaria',
    'CHEMICALS': 'Biotecnología',
    'MEDIA_PRODUCTION': 'Medios de comunicación y difusión',
    'NON_PROFIT': 'Fundaciones y sin fines de lucro'
  };
  return mapping[englishEnum] || null;
}

/**
 * Classify industry from ARCA activity text using LLM API
 * The LLM receives all possible Spanish industry values and chooses the best match directly
 * 
 * @param {string} activityText - The main activity description from ARCA (cleaned)
 * @param {string} companyName - Optional company name for context
 * @returns {Promise<{industry: string|null, hubspotValue: string|null, confidence: string, reasoning: string|null}>}
 */
async function classifyIndustryWithLLM(activityText, companyName = null) {
  if (!activityText || typeof activityText !== 'string' || activityText.trim().length < 10) {
    return {
      industry: null,
      hubspotValue: null,
      confidence: 'none',
      reasoning: 'Activity text too short or invalid'
    };
  }

  // Check for OpenAI API key - In HubSpot custom code, this is configured in workflow settings
  // Go to: Workflow → Custom Code Action → Environment Variables → Add OPENAI_API_KEY
  const openaiApiKey = process.env.OPENAI_API_KEY || 
                       process.env.OPENAI_KEY;
  
  if (!openaiApiKey) {
    console.log('⚠️  LLM Classification: OPENAI_API_KEY not found - falling back to keyword matching');
    return {
      industry: null,
      hubspotValue: null,
      confidence: 'none',
      reasoning: 'OPENAI_API_KEY not configured - use keyword matching'
    };
  }

  // All possible Spanish industry values that can be set in HubSpot
  const availableIndustries = [
    'Tecnología de la información y servicios',
    'Fabricación, Manufactura, Metalúrgica',
    'Logística, almacenamiento, transporte',
    'Agricultura, ganadería, pesca',
    'Alimentos y bebidas',
    'Arquitectura, ingeniería, construcción',
    'Bazar en general',
    'Servicios de consultoría',
    'Medicina, farmacéutica, salud, higiene',
    'Educación en general',
    'Banca, finanzas, seguros',
    'Contabilidad, impuestos, legales',
    'Marketing y publicidad',
    'Hotelería y turismo',
    'Automóviles, autopartes, automotriz',
    'Electrónica, electricidad, energía',
    'Industria textil, moda, indumentaria',
    'Biotecnología',
    'Medios de comunicación y difusión',
    'Fundaciones y sin fines de lucro'
  ];

  const systemPrompt = `Eres un experto clasificador de industrias para empresas argentinas. Tu tarea es analizar la descripción de actividad de ARCA (Administración de Ingresos Brutos de Argentina) y seleccionar la industria que mejor describe la actividad principal de la empresa.

INDUSTRIAS DISPONIBLES (debes elegir exactamente UNA de estas opciones):

1. "Tecnología de la información y servicios"
   - Ejemplos de actividades ARCA: Servicios de consultores en tecnología de la información, Actividades conexas al procesamiento y hospedaje de datos, Desarrollo de software, Servicios informáticos

2. "Fabricación, Manufactura, Metalúrgica"
   - Ejemplos: Fabricación de muebles y partes de muebles, Fabricación de productos metálicos, Metalurgia, Talleres metalúrgicos, Producción industrial

3. "Logística, almacenamiento, transporte"
   - Ejemplos: Transporte de carga, Almacenamiento y depósito, Logística, Servicios de transporte terrestre/marítimo/aéreo, Mensajería

4. "Agricultura, ganadería, pesca"
   - Ejemplos: Agricultura, Ganadería, Pesca, Cultivos, Cría de animales, Agropecuaria, Semillas

5. "Alimentos y bebidas"
   - Ejemplos: Elaboración de productos alimenticios, Matanza de animales y procesamiento de carne, Venta al por mayor de café, té, yerba mate, Frigoríficos, Procesamiento de alimentos

6. "Arquitectura, ingeniería, construcción"
   - Ejemplos: Construcción de obras de ingeniería civil, Desarrollo inmobiliario (construcción de edificios), Arquitectura, Ingeniería, Construcción de viviendas, Obras civiles, Alquiler de maquinaria y equipo, Alquiler de maquinaria y equipo n.c.p., Alquiler de equipo de construcción

7. "Bazar en general"
   - Ejemplos: Venta al por menor de productos diversos sin categoría específica, Venta general de productos variados, Comercio minorista general (cuando no hay categoría específica)

8. "Servicios de consultoría"
   - Ejemplos: Servicios inmobiliarios (corretaje, administración, tasación), Servicios de consultoría empresarial, Asesoramiento, Servicios profesionales de consultoría, Corretaje inmobiliario, Servicios de alquiler (cuando no es específicamente maquinaria de construcción)

9. "Medicina, farmacéutica, salud, higiene"
   - Ejemplos: Venta al por menor/mayor de instrumental médico y odontológico, Venta de artículos ortopédicos, Servicios de acondicionamiento físico/gimnasios, Laboratorios, Clínicas, Farmacias, Productos médicos

10. "Educación en general"
    - Ejemplos: Enseñanza, Educación primaria/secundaria/terciaria, Cursos, Institutos educativos, Capacitación

11. "Banca, finanzas, seguros"
    - Ejemplos: Servicios bancarios, Financieras, Seguros, Créditos, Inversiones, Servicios financieros, Servicios de fideicomisos, Fideicomisos, Fiduciarias

12. "Contabilidad, impuestos, legales"
    - Ejemplos: Servicios contables, Asesoramiento impositivo, Estudios jurídicos, Servicios legales, Administración tributaria
    - NOTA: NO incluir "Servicios de fideicomisos" (eso va en "Banca, finanzas, seguros")

13. "Marketing y publicidad"
    - Ejemplos: Servicios de marketing, Publicidad, Agencias de publicidad, Comunicación, Branding

14. "Hotelería y turismo"
    - Ejemplos: Hoteles, Servicios de alojamiento, Agencias de turismo, Restaurantes, Servicios gastronómicos

15. "Automóviles, autopartes, automotriz"
    - Ejemplos: Venta al por menor de partes, piezas y accesorios nuevos de vehículos, Reparación de carrocerías, Venta de vehículos, Servicios automotrices, Pintura de carrocerías

16. "Electrónica, electricidad, energía"
    - Ejemplos: Venta al por mayor de máquinas y equipo de control y seguridad, Sistemas contra incendios, Equipos eléctricos, Instalaciones eléctricas, Energía, Seguridad electrónica

17. "Industria textil, moda, indumentaria"
    - Ejemplos: Fabricación de prendas de vestir, Industria textil, Confección, Moda, Indumentaria

18. "Biotecnología"
    - Ejemplos: Investigación biotecnológica, Laboratorios biotecnológicos, Productos biotecnológicos

19. "Medios de comunicación y difusión"
    - Ejemplos: Producción de filmes y videocintas, Radio, Televisión, Medios de comunicación, Entretenimiento

20. "Fundaciones y sin fines de lucro"
    - Ejemplos: Fundaciones, Asociaciones sin fines de lucro, ONGs, Cooperativas, Clubes deportivos

REGLAS CRÍTICAS PARA LA CLASIFICACIÓN:

1. **Analiza la actividad principal específica, NO palabras genéricas**: 
   - "Venta al por menor" NO significa automáticamente "Bazar en general"
   - Debes identificar QUÉ se vende específicamente

2. **Distinciones importantes**:
   - "Servicios inmobiliarios" (corretaje, tasación, administración) → "Servicios de consultoría" (NO construcción)
   - "Desarrollo inmobiliario" (construir edificios) → "Arquitectura, ingeniería, construcción"
   - "Alquiler de maquinaria y equipo" o "Alquiler de maquinaria y equipo n.c.p." → "Arquitectura, ingeniería, construcción" (equipos de construcción)
   - "Servicios de fideicomisos" (trusts, fiducia) → "Banca, finanzas, seguros" (NO "Contabilidad, impuestos, legales")
   - "Venta de partes/piezas/accesorios de vehículos" → "Automóviles, autopartes, automotriz" (NO bazar)
   - "Venta de productos médicos/ortopédicos" → "Medicina, farmacéutica, salud, higiene" (NO bazar)
   - "Servicios de gimnasios/acondicionamiento físico" → "Medicina, farmacéutica, salud, higiene" (NO hotelería)
   - "Sistemas contra incendios/seguridad" → "Electrónica, electricidad, energía" (NO construcción)
   - "Venta general de productos diversos sin especificar" → "Bazar en general"

3. **Usa el contexto del nombre de la empresa cuando sea relevante**:
   - Si el nombre menciona específicamente el tipo de negocio (ej: "SISTEMAS CONTRA INCENDIOS", "AUTOPARTES", "ORTOPÉDICOS"), úsalo para interpretar mejor la actividad

4. **Prioriza la actividad específica sobre términos genéricos**:
   - "Venta al por menor de instrumental médico" es MÁS ESPECÍFICO que solo "venta al por menor"
   - "Servicios inmobiliarios" es MÁS ESPECÍFICO que solo "servicios"

5. **"Bazar en general" es SOLO para venta de productos diversos sin categoría específica**:
   - NO uses "Bazar en general" si la actividad menciona un tipo específico de producto (ej: "partes de vehículos", "productos médicos")

INSTRUCCIONES:
- Lee cuidadosamente la actividad ARCA proporcionada
- Considera el nombre de la empresa si está disponible (puede dar contexto)
- Identifica la actividad principal específica
- Elige EXACTAMENTE UNA de las 20 industrias listadas arriba
- Responde SOLO con el texto exacto de la industria entre comillas (ej: "Automóviles, autopartes, automotriz")
- Si ninguna industria es apropiada (muy raro), responde con "UNKNOWN"`;

  const userPrompt = `Actividad ARCA: "${activityText}"${companyName ? `\n\nNombre de la empresa: "${companyName}"` : ''}

Analiza esta actividad y elige la industria que mejor la describe. Responde SOLO con el texto exacto de la industria entre comillas, por ejemplo: "Automóviles, autopartes, automotriz"`;

  try {
    // Use fetch if available (Node.js 18+ or HubSpot environment)
    // Fallback to https module if fetch is not available
    let response;
    if (typeof fetch !== 'undefined') {
      response = await fetch('https://api.openai.com/v1/chat/completions', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${openaiApiKey}`
        },
        body: JSON.stringify({
          model: 'gpt-4o-mini', // Using mini for cost efficiency
          messages: [
            { role: 'system', content: systemPrompt },
            { role: 'user', content: userPrompt }
          ],
          temperature: 0.3, // Lower temperature for more consistent classifications
          max_tokens: 80 // Need enough tokens for Spanish industry value
        })
      });
    } else {
      // Fallback for environments without fetch (use https module)
      // https module is required at top level, so it should be available here
      const responsePromise = new Promise((resolve, reject) => {
        const postData = JSON.stringify({
          model: 'gpt-4o-mini',
          messages: [
            { role: 'system', content: systemPrompt },
            { role: 'user', content: userPrompt }
          ],
          temperature: 0.3,
          max_tokens: 80
        });
        
        const options = {
          hostname: 'api.openai.com',
          path: '/v1/chat/completions',
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'Authorization': `Bearer ${openaiApiKey}`,
            'Content-Length': Buffer.byteLength(postData)
          }
        };
        
        const req = httpsModule.request(options, (res) => {
          let data = '';
          res.on('data', (chunk) => { data += chunk; });
          res.on('end', () => {
            resolve({
              ok: res.statusCode === 200,
              status: res.statusCode,
              json: () => Promise.resolve(JSON.parse(data)),
              text: () => Promise.resolve(data)
            });
          });
        });
        
        req.on('error', reject);
        req.write(postData);
        req.end();
      });
      
      response = await responsePromise;
    }

    if (!response.ok) {
      const errorText = await response.text();
      console.log(`⚠️  LLM API error: ${response.status} - ${errorText.substring(0, 200)}`);
      return {
        industry: null,
        hubspotValue: null,
        confidence: 'none',
        reasoning: `API error: ${response.status}`
      };
    }

    const data = await response.json();
    const llmResponse = data.choices[0]?.message?.content?.trim() || '';
    
    // Extract the Spanish industry value from LLM response (may include quotes or extra text)
    let selectedIndustry = null;
    const cleanedResponse = llmResponse.replace(/^["']|["']$/g, '').trim();
    
    // Try exact match first (most common case)
    for (const industry of availableIndustries) {
      if (cleanedResponse === industry || 
          cleanedResponse.toLowerCase() === industry.toLowerCase() ||
          llmResponse.includes(industry)) {
        selectedIndustry = industry;
        break;
      }
    }
    
    // If no exact match, try partial matching
    if (!selectedIndustry) {
      for (const industry of availableIndustries) {
        const industryKeywords = industry.toLowerCase().split(/[,\s]+/).filter(k => k.length > 3);
        const responseLower = cleanedResponse.toLowerCase();
        const matchingKeywords = industryKeywords.filter(keyword => 
          responseLower.includes(keyword)
        );
        if (matchingKeywords.length >= Math.min(2, industryKeywords.length)) {
          selectedIndustry = industry;
          break;
        }
      }
    }
    
    if (!selectedIndustry) {
      return {
        industry: null,
        hubspotValue: null,
        confidence: 'low',
        reasoning: `LLM responded: "${llmResponse}" but couldn't match to any valid industry from the list`
      };
    }

    // Map back to enum for internal tracking (optional)
    const enumMapping = {
      'Tecnología de la información y servicios': 'INFORMATION_TECHNOLOGY_AND_SERVICES',
      'Fabricación, Manufactura, Metalúrgica': 'MANUFACTURING',
      'Logística, almacenamiento, transporte': 'LOGISTICS_AND_SUPPLY_CHAIN',
      'Agricultura, ganadería, pesca': 'AGRICULTURE',
      'Alimentos y bebidas': 'FOOD_AND_BEVERAGE',
      'Arquitectura, ingeniería, construcción': 'CONSTRUCTION',
      'Bazar en general': 'RETAIL',
      'Servicios de consultoría': 'PROFESSIONAL_SERVICES',
      'Medicina, farmacéutica, salud, higiene': 'HEALTHCARE',
      'Educación en general': 'EDUCATION',
      'Banca, finanzas, seguros': 'FINANCIAL_SERVICES',
      'Contabilidad, impuestos, legales': 'LEGAL_SERVICES',
      'Marketing y publicidad': 'MARKETING_AND_ADVERTISING',
      'Hotelería y turismo': 'HOSPITALITY',
      'Automóviles, autopartes, automotriz': 'AUTOMOTIVE',
      'Electrónica, electricidad, energía': 'ENERGY',
      'Industria textil, moda, indumentaria': 'TEXTILES',
      'Biotecnología': 'CHEMICALS',
      'Medios de comunicación y difusión': 'MEDIA_PRODUCTION',
      'Fundaciones y sin fines de lucro': 'NON_PROFIT'
    };
    
    const inferredEnum = enumMapping[selectedIndustry] || null;

    return {
      industry: inferredEnum,
      hubspotValue: selectedIndustry, // Direct Spanish value - ready for HubSpot
      confidence: 'high',
      reasoning: `LLM selected: "${selectedIndustry}" (response: "${llmResponse}")`
    };

  } catch (error) {
    console.log(`⚠️  LLM classification error: ${error.message}`);
    return {
      industry: null,
      hubspotValue: null,
      confidence: 'none',
      reasoning: `Error: ${error.message}`
    };
  }
}

// Industry keyword mapping for fallback keyword matching
const INDUSTRY_KEYWORDS = {
  'INFORMATION_TECHNOLOGY_AND_SERVICES': [
    'software', 'sistemas', 'informatica', 'informática', 'desarrollo', 'programacion',
    'tecnologia', 'servicios informaticos', 'cloud computing', 'saas', 'plataforma',
    'desarrollo software', 'desarrollo web', 'computo', 'consultores en informática'
  ],
  'MANUFACTURING': [
    'manufactura', 'fabrica', 'produccion', 'industrial', 'taller', 'maquinaria',
    'fabricación', 'metalurgica', 'metalúrgica', 'muebles', 'carpinteria'
  ],
  'LOGISTICS_AND_SUPPLY_CHAIN': [
    'logistica', 'transporte', 'distribucion', 'envios', 'almacen', 'deposito'
  ],
  'AGRICULTURE': [
    'agro', 'agricola', 'ganaderia', 'agricultura', 'cultivo', 'semillas', 'ganado'
  ],
  'FOOD_AND_BEVERAGE': [
    'alimentos', 'bebidas', 'restaurante', 'gastronomia', 'cocina', 'frigorifico',
    'matanza', 'procesamiento de carne', 'cafe', 'yerba mate'
  ],
  'CONSTRUCTION': [
    'construccion', 'obra', 'arquitectura', 'ingenieria', 'desarrollo inmobiliario',
    'edificios', 'vivienda', 'obras de ingeniería', 'alquiler de maquinaria', 'alquiler de equipo',
    'alquiler de maquinaria y equipo', 'alquiler maquinaria', 'alquiler equipo', 'rental de maquinaria',
    'rental de equipo', 'maquinaria de construccion', 'equipo de construccion', 'alquiler ncp'
  ],
  'RETAIL': [
    'retail', 'comercio', 'tienda', 'venta al por menor', 'venta al por mayor',
    'cosmeticos', 'belleza', 'estetica', 'estética'
  ],
  'PROFESSIONAL_SERVICES': [
    'servicios', 'consultoria', 'asesoria', 'estudio', 'soluciones',
    'servicios inmobiliarios', 'corretaje inmobiliario', 'tasación', 'appraisal',
    'alquiler', 'rental', 'alquileres', 'servicios de alquiler'
  ],
  'HEALTHCARE': [
    'salud', 'medico', 'clinica', 'hospital', 'farmacia', 'medicina',
    'consultorio', 'geriátrica', 'gimnasio', 'fitness', 'wellness',
    'instrumental médico', 'ortopédicos', 'prótesis', 'termómetros'
  ],
  'EDUCATION': [
    'educacion', 'escuela', 'colegio', 'universidad', 'academia', 'instituto'
  ],
  'FINANCIAL_SERVICES': [
    'financiero', 'banco', 'credito', 'seguros', 'finanzas', 'inversion',
    'fideicomiso', 'fideicomisos', 'fiducia', 'trust', 'servicios fiduciarios'
  ],
  'LEGAL_SERVICES': [
    'legal', 'abogado', 'juridico', 'estudio juridico', 'servicios jurídicos'
  ],
  'MARKETING_AND_ADVERTISING': [
    'marketing', 'publicidad', 'advertising', 'agencia', 'comunicacion'
  ],
  'HOSPITALITY': [
    'hotel', 'turismo', 'viajes', 'resort', 'alojamiento', 'agencia de viajes'
  ],
  'AUTOMOTIVE': [
    'automotor', 'auto', 'vehiculo', 'concesionario', 'repuestos', 'automotriz',
    'reparación de carrocerías', 'partes', 'piezas', 'accesorios', 'partes y piezas'
  ],
  'ENERGY': [
    'energia', 'electricidad', 'gas', 'sistemas contra incendios', 'seguridad',
    'equipo de control y seguridad'
  ],
  'TEXTILES': [
    'textil', 'moda', 'ropa', 'indumentaria', 'confeccion'
  ],
  'CHEMICALS': [
    'quimico', 'quimica', 'laboratorio'
  ],
  'MEDIA_PRODUCTION': [
    'media', 'produccion', 'cine', 'television', 'radio', 'filmes', 'videocintas'
  ],
  'NON_PROFIT': [
    'ong', 'fundacion', 'asociacion', 'sin fines de lucro', 'cooperativa', 'club'
  ]
};

const COMPANY_NAME_STRONG_INDICATORS = {
  'AGRICULTURE': ['agro', 'semillas'],
  'RETAIL': ['esthetic', 'estetica'],
  'FOOD_AND_BEVERAGE': ['frigorifico', 'frigorífico'],
  'MANUFACTURING': ['metalurgica', 'metalúrgica']
};

function inferIndustryFromCompanyName(companyName) {
  if (!companyName || typeof companyName !== 'string') return null;
  const nameLower = companyName.toLowerCase();
  for (const [industry, keywords] of Object.entries(COMPANY_NAME_STRONG_INDICATORS)) {
    for (const keyword of keywords) {
      const keywordRegex = new RegExp(`\\b${keyword.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}\\b`, 'i');
      if (keywordRegex.test(nameLower)) return industry;
    }
  }
  return null;
}

function inferIndustryFromText(text, isCompanyName = false) {
  if (!text || typeof text !== 'string') return null;
  const textLower = text.toLowerCase().trim();
  
  if (isCompanyName) {
    const namePattern = /^[\d\s-]+[A-Z\s]+$/i;
    if (namePattern.test(text.trim()) && textLower.length < 50) return null;
    const hasBusinessKeywords = /(s\.?a\.?|s\.?r\.?l\.?|ltda|inc|corp|company|empresa)/i.test(text);
    if (!hasBusinessKeywords && textLower.length < 30) return null;
  }
  
  const industryScores = {};
  for (const [industry, keywords] of Object.entries(INDUSTRY_KEYWORDS)) {
    let score = 0;
    const matchedKeywords = [];
    for (const keyword of keywords) {
      const escapedKeyword = keyword.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
      if (keyword.includes(' ')) {
        // For multi-word phrases, try both word boundary matching and flexible matching
        // Word boundary matching (strict)
        const phraseRegex = new RegExp(`\\b${escapedKeyword}\\b`, 'i');
        // Flexible matching (allows punctuation after the phrase, like "equipo n.c.p.")
        const flexiblePhraseRegex = new RegExp(`\\b${escapedKeyword}(?=\\s|[,.;:!?]|$)`, 'i');
        if (phraseRegex.test(textLower) || flexiblePhraseRegex.test(textLower)) {
          score += 2;
          matchedKeywords.push(keyword);
        }
      } else {
        const keywordRegex = new RegExp(`\\b${escapedKeyword}\\b`, 'i');
        if (keywordRegex.test(textLower)) {
          score += 1;
          matchedKeywords.push(keyword);
        }
      }
    }
    if (score > 0) industryScores[industry] = { score, matchedKeywords };
  }
  
  if (Object.keys(industryScores).length === 0) return null;
  
  const minScoreThreshold = 2;
  const validIndustries = Object.entries(industryScores).filter(([, data]) => 
    data.score >= minScoreThreshold
  );
  
  if (validIndustries.length === 0) return null;
  
  const bestIndustry = validIndustries.reduce((a, b) => 
    a[1].score > b[1].score ? a : b
  );
  
  return bestIndustry[0];
}

async function searchCompanyDomain(companyName) {
  if (!companyName || companyName.trim() === '') return null;
  
  try {
    let cleanedName = companyName
      .replace(/^\d+\s*-\s*/i, '')
      .replace(/[^\w\s]/g, ' ')
      .trim();
    
    const stopWords = new Set(['the', 'and', 'or', 'of', 'a', 'an', 'in', 'on', 'at', 'to', 'for', 'de', 'del', 'la', 'el', 'los', 'las', 'club', 'sociedad']);
    const words = cleanedName
      .split(/\s+/)
      .filter(word => word.length > 2 && !stopWords.has(word.toLowerCase()))
      .slice(0, 4);
    
    if (words.length === 0) return null;
    
    const allWords = words.join('').toLowerCase();
    const firstLetters = words.map(w => w[0]).join('').toLowerCase();
    const domainPatterns = [allWords, firstLetters].filter(p => p.length >= 3);
    const tlds = ['com.ar', 'ar', 'com', 'net', 'org'];
    const potentialDomains = [];
    
    for (const pattern of domainPatterns) {
      for (const tld of tlds) {
        potentialDomains.push(`${pattern}.${tld}`);
      }
    }
    
    for (const domain of [...new Set(potentialDomains)].slice(0, 15)) {
      try {
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), 2000);
        
        try {
          const response = await fetch(`https://${domain}`, {
            method: 'GET',
            headers: { 'User-Agent': 'Mozilla/5.0 (compatible; HubSpotBot/1.0)' },
            signal: controller.signal,
            redirect: 'follow'
          });
          
          clearTimeout(timeoutId);
          
          if (response.ok) {
            const html = await response.text();
            const htmlLower = html.toLowerCase();
            const wordsInWebsite = words.filter(word => htmlLower.includes(word.toLowerCase()));
            
            if (wordsInWebsite.length >= 2 || words.length === 1) {
              console.log(`✅ DOMAIN FOUND: ${domain}`);
              return domain;
            }
          }
        } catch (fetchError) {
          clearTimeout(timeoutId);
          if (fetchError.name !== 'AbortError') continue;
        }
      } catch (error) {
        continue;
      }
    }
    
    return null;
  } catch (error) {
    console.log(`⚠️  SEARCH ERROR: ${error.message}`);
    return null;
  }
}

async function searchCompanyByCUIT(cuit, companyName = null) {
  if (!cuit || cuit.trim() === '') return null;
  
  const normalizedCuit = cuit.replace(/[-\s.]/g, '');
  if (normalizedCuit.length !== 11 || !/^\d+$/.test(normalizedCuit)) {
    console.log(`⚠️  CUIT SEARCH SKIPPED: Invalid CUIT format "${cuit}"`);
    return null;
  }
  
  const formattedCuit = `${normalizedCuit.substring(0, 2)}-${normalizedCuit.substring(2, 10)}-${normalizedCuit.substring(10)}`;
  console.log(`🔍 CUIT search: ${formattedCuit}${companyName ? ` (company: ${companyName.substring(0, 50)})` : ''}`);
  
  if (typeof fetch === 'undefined') {
    console.log(`⚠️  CUIT SEARCH SKIPPED: fetch() API not available`);
    return null;
  }
  
  try {
    let foundActivity = null;
    let foundCompanyName = null;
    
    const urlsToTry = [];
    if (companyName && companyName.trim() !== '') {
      const companySlug = companyName
        .toLowerCase()
        .replace(/[^a-z0-9]+/g, '-')
        .replace(/^-+|-+$/g, '')
        .substring(0, 100);
      if (companySlug.length >= 3) {
        urlsToTry.push(`https://www.dateas.com/es/empresa/${companySlug}-${normalizedCuit}`);
      }
    }
    urlsToTry.push(`https://www.dateas.com/es/empresa/${normalizedCuit}`);
    
    for (const url of urlsToTry) {
      try {
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), 5000);
        
        const response = await fetch(url, {
          method: 'GET',
          headers: {
            'User-Agent': 'Mozilla/5.0 (compatible; HubSpotBot/1.0)',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'es-AR,es;q=0.9,en;q=0.8'
          },
          signal: controller.signal
        });
        
        clearTimeout(timeoutId);
        
        if (response.ok) {
          const html = await response.text();
          
          const titleMatch = html.match(/<title[^>]*>([^<]+?)\s*-\s*CUIT[^<]*<\/title>/i);
          if (titleMatch && titleMatch[1]) {
            foundCompanyName = titleMatch[1].trim()
              .replace(/<[^>]+>/g, ' ')
              .replace(/&[a-z]+;/gi, ' ')
              .replace(/\s+/g, ' ')
              .trim()
              .substring(0, 200);
          }
          
          const htmlText = html
            .replace(/<script[^>]*>[\s\S]*?<\/script>/gi, ' ')
            .replace(/<style[^>]*>[\s\S]*?<\/style>/gi, ' ')
            .replace(/<[^>]+>/g, ' ')
            .replace(/\s+/g, ' ');
          
          const activityMatch = htmlText.match(/actividad\s+u\s+ocupaci[oó]n[:\s,]+([^<\n]{20,300})/i);
          if (activityMatch && activityMatch[1]) {
            let rawActivity = activityMatch[1].trim()
              .replace(/&[a-z]+;/gi, ' ')
              .replace(/[\][(){}]/g, ' ')
              .replace(/\s+/g, ' ');
            
            const administrativePatterns = [
              /buscar por actividad/i,
              /ganancias/i,
              /iva/i,
              /monotributo/i,
              /inscripto/i,
              /integra/i,
              /empleador/i,
              /si esta persona/i
            ];
            
            let cleanActivity = rawActivity;
            for (const pattern of administrativePatterns) {
              const match = cleanActivity.match(pattern);
              if (match && match.index) {
                cleanActivity = cleanActivity.substring(0, match.index).trim();
                break;
              }
            }
            
            foundActivity = cleanActivity
              .replace(/[.,;:\s]+$/g, '')
              .substring(0, 200)
              .trim();

            if (foundActivity.length >= 10 && /[A-Za-z]/.test(foundActivity)) {
              console.log(`✅ CUIT search success: activity found`);
              return {
                domain: null,
                companyName: foundCompanyName,
                websiteContent: `Actividad: ${foundActivity}`,
                activity: foundActivity
              };
            }
          }
        }
      } catch (error) {
        if (error.name !== 'AbortError') continue;
      }
    }
    
    if (foundCompanyName) {
      return {
        domain: null,
        companyName: foundCompanyName,
        websiteContent: null,
        activity: null
      };
    }
    
    return null;
  } catch (error) {
    console.log(`⚠️  CUIT search error: ${error.message}`);
    return null;
  }
}

async function testFetchAvailability() {
  try {
    if (typeof fetch === 'undefined') return false;
    
    const testUrl = 'https://httpbin.org/get';
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 5000);
    
    try {
      const response = await fetch(testUrl, {
        method: 'GET',
        headers: { 'User-Agent': 'Mozilla/5.0 (compatible; HubSpotBot/1.0)' },
        signal: controller.signal
      });
      
      clearTimeout(timeoutId);
      return response.ok;
    } catch (testError) {
      clearTimeout(timeoutId);
      return false;
    }
  } catch (error) {
    return false;
  }
}

async function fetchWebsiteContent(url) {
  try {
    let fullUrl = url;
    if (!url.startsWith('http://') && !url.startsWith('https://')) {
      fullUrl = `https://${url}`;
    }
    
    let controller;
    let timeoutId;
    
    try {
      if (typeof AbortController !== 'undefined') {
        controller = new AbortController();
        timeoutId = setTimeout(() => controller.abort(), 10000);
      }
      
      const fetchOptions = {
        method: 'GET',
        headers: {
          'User-Agent': 'Mozilla/5.0 (compatible; HubSpotBot/1.0)',
          'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
          'Accept-Language': 'es-AR,es;q=0.9,en;q=0.8'
        }
      };
      
      if (controller) fetchOptions.signal = controller.signal;
      
      const response = await fetch(fullUrl, fetchOptions);
      
      if (timeoutId) clearTimeout(timeoutId);
      
      if (!response.ok) {
        console.log(`⚠️  Website fetch failed: HTTP ${response.status}`);
        return null;
      }
      
      const html = await response.text();
      if (!html || html.length === 0) return null;
      
      let text = html
        .replace(/<script[^>]*>[\s\S]*?<\/script>/gi, ' ')
        .replace(/<style[^>]*>[\s\S]*?<\/style>/gi, ' ')
        .replace(/<[^>]+>/g, ' ')
        .replace(/\s+/g, ' ')
        .trim()
        .substring(0, 50000);
      
      if (text.length === 0) return null;
      
      console.log(`✅ Website content fetched: ${text.length} characters`);
      return text;
      
    } catch (fetchError) {
      if (timeoutId) clearTimeout(timeoutId);
      if (fetchError.name === 'AbortError') {
        console.log(`⚠️  Website fetch timeout: ${fullUrl}`);
      } else {
        console.log(`⚠️  Error fetching website: ${fetchError.message}`);
      }
      return null;
    }
  } catch (error) {
    console.log(`⚠️  Unexpected error in fetchWebsiteContent: ${error.message}`);
    return null;
  }
}

/**
 * Send Slack notification for industry enrichment
 * @param {Object} notification - Notification object with type, title, message, and details
 */
async function sendSlackNotification(notification) {
  const slackWebhookUrl = process.env.SlackWebhookUrl;
  
  if (!slackWebhookUrl) {
    console.log('⚠️  SlackWebhookUrl not configured - skipping notification');
    return;
  }
  
  let slackMessage;
  
  if (notification.type === 'success' && (notification.details.industriaWasChanged || notification.details.arcaActivityWasEnriched)) {
    // Industry enrichment or ARCA activity enrichment notification
    slackMessage = {
      channel: 'C07RY5760TZ', // Explicitly set channel for intercom_mixpanel_notification
      text: notification.title,
      attachments: [
        {
          color: getSlackColor(notification.type),
          fields: [
            {
              title: '🏢 Company',
              value: `<https://app.hubspot.com/contacts/19877595/company/${notification.details.companyId}|${notification.details.companyName || 'Unknown'}>`,
              short: true
            },
            {
              title: '👤 Company Owner',
              value: notification.details.companyOwnerName || 'No Owner',
              short: true
            },
            {
              title: '🏭 Industria Change',
              value: notification.details.industriaWasChanged && notification.details.newIndustria
                ? `${notification.details.oldIndustria} → ${notification.details.newIndustria}`
                : notification.details.arcaActivityWasEnriched
                  ? `${notification.details.oldIndustria} (no change - ARCA activity enriched)`
                  : `${notification.details.oldIndustria} (no change)`,
              short: true
            },
            {
              title: '🔍 Enrichment Method',
              value: notification.details.enrichmentMethod || 'unknown',
              short: true
            },
            {
              title: '📋 ARCA Activity Text',
              value: notification.details.arcaActivityText || 'N/A',
              short: false
            },
            {
              title: '🏷️ Industry Enum',
              value: notification.details.inferredIndustryEnum || 'N/A',
              short: true
            },
            {
              title: '🌐 Domain',
              value: notification.details.domain || 'N/A',
              short: true
            },
            {
              title: '🆔 CUIT',
              value: notification.details.cuit || 'N/A',
              short: true
            },
            {
              title: '📋 Type Change',
              value: notification.details.typeWasInferred 
                ? `${notification.details.oldType} → ${notification.details.newType} (${notification.details.typeMatchType})`
                : `${notification.details.oldType} (no change)`,
              short: true
            },
            ...(notification.details.llmReasoning ? [{
              title: '🤖 LLM Reasoning',
              value: notification.details.llmReasoning.substring(0, 500) + (notification.details.llmReasoning.length > 500 ? '...' : ''),
              short: false
            }] : []),
            {
              title: '💡 Reason',
              value: notification.details.changeReason || 'Auto-populated industria from ARCA activity',
              short: false
            }
          ],
          timestamp: Math.floor(Date.now() / 1000),
          footer: 'HubSpot Workflow Automation',
          footer_icon: 'https://hubspot.com/favicon.ico'
        }
      ]
    };
  } else {
    // Generic notification format
    slackMessage = {
      channel: 'C07RY5760TZ',
      text: notification.title,
      attachments: [
        {
          color: getSlackColor(notification.type),
          text: notification.message || 'Industry enrichment completed',
          timestamp: Math.floor(Date.now() / 1000),
          footer: 'HubSpot Workflow Automation',
          footer_icon: 'https://hubspot.com/favicon.ico'
        }
      ]
    };
  }

  const response = await fetch(slackWebhookUrl, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(slackMessage)
  });

  if (!response.ok) {
    throw new Error(`Slack API error: ${response.status} ${response.statusText}`);
  }
}

/**
 * Get Slack color for notification type
 * @param {string} type - Notification type (success, warning, error, info)
 * @returns {string} Slack color code
 */
function getSlackColor(type) {
  switch (type) {
    case 'success': return 'good';
    case 'warning': return 'warning';
    case 'error': return 'danger';
    case 'info': return '#36a64f';
    default: return '#36a64f';
  }
}

// Main export function for HubSpot workflow
exports.main = async (event, callback) => {
  const client = new hubspot.Client({
    accessToken: process.env.ColppyCRMAutomations
  });

  try {
    // Handle both test mode and production mode event structures
    const companyId = event.object?.objectId || event.inputFields?.objectId || event.objectId;
    
    if (!companyId) {
      const errorMsg = 'Company ID not found in event object. Event structure: ' + JSON.stringify(event, null, 2);
      console.error('❌ MISSING COMPANY ID:', errorMsg);
      callback(new Error(errorMsg));
      return;
    }
    
    const companyIdString = String(companyId);

    console.log('='.repeat(80));
    console.log('🚀 INDUSTRY ENRICHMENT WORKFLOW STARTED');
    console.log('='.repeat(80));
    console.log(`📋 Company ID: ${companyIdString}`);
    console.log(`📅 Timestamp: ${new Date().toISOString()}`);
    console.log('='.repeat(80));

    // Get current company properties
    const currentCompany = await client.crm.companies.basicApi.getById(companyIdString, [
      'name', 'domain', 'cuit', 'industria', 'type', 'hubspot_owner_id', 'actividad_de_la_compania_segun_arca'
    ]);
    
    const companyName = currentCompany.properties.name;
    const companyDomain = currentCompany.properties.domain;
    const companyCuit = currentCompany.properties.cuit;
    let companyIndustry = currentCompany.properties.industria;
    const currentCompanyType = currentCompany.properties.type;
    const existingArcaActivity = currentCompany.properties.actividad_de_la_compania_segun_arca;
    
    // Helper function to get owner name
    async function getOwnerName(ownerId) {
      if (!ownerId) return 'No Owner';
      try {
        const response = await fetch(`https://api.hubspot.com/crm/v3/owners/${ownerId}`, {
          headers: {
            'Authorization': `Bearer ${process.env.ColppyCRMAutomations}`,
            'Content-Type': 'application/json'
          }
        });
        
        if (response.ok) {
          const data = await response.json();
          const firstName = data.firstName || '';
          const lastName = data.lastName || '';
          return `${firstName} ${lastName}`.trim() || `Owner ID: ${ownerId}`;
        }
        return `Owner ID: ${ownerId}`;
      } catch (error) {
        return `Owner ID: ${ownerId}`;
      }
    }
    
    const companyOwnerName = currentCompany.properties.hubspot_owner_id 
      ? await getOwnerName(currentCompany.properties.hubspot_owner_id)
      : 'No Owner';

    console.log(`📊 Current Company: ${companyName}`);
    console.log(`   Domain: ${companyDomain || 'NULL'}`);
    console.log(`   CUIT: ${companyCuit || 'NULL'}`);
    console.log(`   Industria: ${companyIndustry || 'NULL'}`);
    console.log(`   Type: ${currentCompanyType || 'NULL'}`);

    // ========================================================================
    // INDUSTRY ENRICHMENT: Auto-populate industria field if NULL/EMPTY
    // ========================================================================
    const isIndustriaPopulated = companyIndustry && 
                                  typeof companyIndustry === 'string' && 
                                  companyIndustry.trim() !== '' &&
                                  companyIndustry.trim() !== 'null' &&
                                  companyIndustry.trim() !== 'undefined';
    
    let inferredIndustryEnum = null;
    let enrichmentMethod = null;
    let arcaActivityText = null; // Track ARCA activity text for notification
    let llmReasoning = null; // Track LLM reasoning if LLM was used
    let originalIndustria = companyIndustry || 'NULL'; // Track original for notification
    let newIndustria = null; // Track new value for notification
    let arcaActivityWasEnriched = false; // Track if ARCA activity was just enriched (separate from industria enrichment)
    
    if (!isIndustriaPopulated) {
      console.log(`🔍 INDUSTRY ENRICHMENT: Industria field is NULL/EMPTY - attempting enrichment`);
      
      // Method 0: Use existing ARCA activity if available (most efficient - avoids CUIT search)
      if (!inferredIndustryEnum && existingArcaActivity && existingArcaActivity.trim() !== '' && 
          existingArcaActivity.trim() !== 'null' && existingArcaActivity.trim() !== 'undefined') {
        console.log(`📋 USING EXISTING ARCA ACTIVITY: ARCA activity field already populated - using for industry inference`);
        console.log(`   Activity: "${existingArcaActivity.substring(0, 80)}${existingArcaActivity.length > 80 ? '...' : ''}"`);
        
        // Track ARCA activity text for notification
        arcaActivityText = existingArcaActivity;
        
        // FIRST: Try LLM-based classification if activity text is available
        console.log(`🤖 Attempting LLM-based industry classification from existing ARCA activity...`);
        const llmResult = await classifyIndustryWithLLM(existingArcaActivity, companyName);
        
        if (llmResult.industry && llmResult.confidence === 'high') {
          inferredIndustryEnum = llmResult.industry;
          enrichmentMethod = 'LLM classification (existing ARCA activity)';
          llmReasoning = llmResult.reasoning; // Track LLM reasoning for notification
          console.log(`✅ LLM Industry Classification: ${inferredIndustryEnum} → "${llmResult.hubspotValue}"`);
          if (llmResult.reasoning) {
            console.log(`💭 LLM Reasoning: ${llmResult.reasoning}`);
          }
        } else if (llmResult.reasoning && !llmResult.reasoning.includes('OPENAI_API_KEY not configured')) {
          console.log(`⚠️  LLM classification failed: ${llmResult.reasoning} - falling back to keyword matching`);
        }
        
        // FALLBACK: Use keyword-based classification if LLM failed or not available
        if (!inferredIndustryEnum) {
          const contentToAnalyze = `Actividad: ${existingArcaActivity}`;
          inferredIndustryEnum = inferIndustryFromText(contentToAnalyze, false);
          
          if (!inferredIndustryEnum && companyName) {
            inferredIndustryEnum = inferIndustryFromCompanyName(companyName);
            if (inferredIndustryEnum) {
              enrichmentMethod = 'existing ARCA activity (company name strong indicator)';
              console.log(`✅ Industry inferred from company name strong indicator: ${inferredIndustryEnum}`);
            } else {
              inferredIndustryEnum = inferIndustryFromText(companyName, true);
              if (inferredIndustryEnum) {
                enrichmentMethod = 'existing ARCA activity (company name analysis)';
                console.log(`✅ Industry inferred from company name: ${inferredIndustryEnum}`);
              }
            }
          }
          
          if (inferredIndustryEnum && enrichmentMethod !== 'existing ARCA activity (company name strong indicator)' && 
              enrichmentMethod !== 'LLM classification (existing ARCA activity)') {
            enrichmentMethod = 'existing ARCA activity (keyword matching)';
            console.log(`✅ Industry inferred: ${inferredIndustryEnum} (from existing ARCA activity via keyword matching)`);
          }
        }
      }
      
      // Method 1: Try website scraping if domain exists
      if (!inferredIndustryEnum && companyDomain && companyDomain.trim() !== '') {
        console.log(`🌐 Attempting website scraping for domain: ${companyDomain}`);
        const websiteContent = await fetchWebsiteContent(companyDomain);
        
        if (websiteContent) {
          console.log(`📄 Website content retrieved: ${websiteContent.length} characters`);
          inferredIndustryEnum = inferIndustryFromText(websiteContent, false);
          if (inferredIndustryEnum) {
            enrichmentMethod = 'website scraping';
            console.log(`✅ Industry inferred from website: ${inferredIndustryEnum}`);
            // Use existing ARCA activity if available for notification context
            if (!arcaActivityText && existingArcaActivity) {
              arcaActivityText = existingArcaActivity;
            }
          }
        }
      }
      
      // Method 2: Search using CUIT (when domain is missing AND ARCA activity is not available)
      if (!inferredIndustryEnum && !companyDomain && companyCuit && companyCuit.trim() !== '') {
        console.log(`🔍 CUIT SEARCH: Attempting to find company information using CUIT ${companyCuit}`);
        
        if (typeof exports._cuitFetchTested === 'undefined') {
          exports._cuitFetchTested = true;
          const fetchWorks = await testFetchAvailability();
          if (!fetchWorks) {
            console.log(`⚠️  CUIT SEARCH: fetch() may not work in this environment`);
          }
        }
        
        const cuitResult = await searchCompanyByCUIT(companyCuit, companyName);
        
        if (cuitResult && cuitResult.domain) {
          console.log(`✅ CUIT SEARCH SUCCESS: Found domain ${cuitResult.domain}`);
          
          try {
            await client.crm.companies.basicApi.update(companyIdString, {
              properties: { domain: cuitResult.domain }
            });
            console.log(`✅ DOMAIN UPDATED FROM CUIT: ${cuitResult.domain}`);
            
            const websiteContent = cuitResult.websiteContent || await fetchWebsiteContent(cuitResult.domain);
            if (websiteContent) {
              inferredIndustryEnum = inferIndustryFromText(websiteContent, false);
              if (inferredIndustryEnum) {
                enrichmentMethod = 'website scraping (via CUIT search)';
                console.log(`✅ Industry inferred from CUIT-found domain: ${inferredIndustryEnum}`);
              }
            }
          } catch (updateError) {
            console.log(`⚠️  Could not update domain field: ${updateError.message}`);
          }
        } else if (cuitResult && (cuitResult.websiteContent || cuitResult.activity)) {
          // Track ARCA activity text for notification (use original before cleaning)
          if (cuitResult.activity) {
            arcaActivityText = cuitResult.activity;
          }
          
          // Save cleaned activity text to HubSpot field
          if (cuitResult.activity) {
            try {
              let cleanActivity = cuitResult.activity;
              const administrativePatterns = [
                /buscar por actividad/i,
                /ganancias/i,
                /iva/i,
                /monotributo/i,
                /inscripto/i,
                /integra/i,
                /empleador/i,
                /si esta persona/i
              ];
              
              for (const pattern of administrativePatterns) {
                const match = cleanActivity.match(pattern);
                if (match && match.index) {
                  cleanActivity = cleanActivity.substring(0, match.index).trim();
                  break;
                }
              }
              
              cleanActivity = cleanActivity.replace(/[.,;:\s]+$/g, '').trim();
              
              // Update arcaActivityText to use cleaned version for notification (matches what's saved in HubSpot)
              arcaActivityText = cleanActivity;
              
              await client.crm.companies.basicApi.update(companyIdString, {
                properties: {
                  actividad_de_la_compania_segun_arca: cleanActivity
                }
              });
              console.log(`✅ ACTIVIDAD SAVED: Cleaned activity text saved: "${cleanActivity.substring(0, 60)}..."`);
            } catch (updateError) {
              console.log(`⚠️  Could not update actividad_de_la_compania_segun_arca field: ${updateError.message}`);
            }
          }
          
          // FIRST: Try LLM-based classification if activity text is available
          if (cuitResult.activity) {
            console.log(`🤖 Attempting LLM-based industry classification from ARCA activity...`);
            const llmResult = await classifyIndustryWithLLM(cuitResult.activity, companyName);
            
            if (llmResult.industry && llmResult.confidence === 'high') {
              inferredIndustryEnum = llmResult.industry;
              enrichmentMethod = 'LLM classification (ARCA activity)';
              llmReasoning = llmResult.reasoning; // Track LLM reasoning for notification
              console.log(`✅ LLM Industry Classification: ${inferredIndustryEnum} → "${llmResult.hubspotValue}"`);
              if (llmResult.reasoning) {
                console.log(`💭 LLM Reasoning: ${llmResult.reasoning}`);
              }
            } else if (llmResult.reasoning && !llmResult.reasoning.includes('OPENAI_API_KEY not configured')) {
              console.log(`⚠️  LLM classification failed: ${llmResult.reasoning} - falling back to keyword matching`);
            }
          }
          
          // FALLBACK: Use keyword-based classification if LLM failed or not available
          if (!inferredIndustryEnum) {
            const contentToAnalyze = cuitResult.websiteContent || (cuitResult.activity ? `Actividad: ${cuitResult.activity}` : null);
            if (contentToAnalyze) {
              inferredIndustryEnum = inferIndustryFromText(contentToAnalyze, false);
              
              if (!inferredIndustryEnum && cuitResult.activity && companyName) {
                inferredIndustryEnum = inferIndustryFromCompanyName(companyName);
                if (inferredIndustryEnum) {
                  enrichmentMethod = 'CUIT database activity (company name strong indicator)';
                  console.log(`✅ Industry inferred from company name strong indicator: ${inferredIndustryEnum}`);
                } else {
                  inferredIndustryEnum = inferIndustryFromText(companyName, true);
                  if (inferredIndustryEnum) {
                    enrichmentMethod = 'CUIT database activity (company name analysis)';
                    console.log(`✅ Industry inferred from company name: ${inferredIndustryEnum}`);
                  }
                }
              }
              
              if (inferredIndustryEnum && enrichmentMethod !== 'CUIT database activity (company name strong indicator)' && enrichmentMethod !== 'LLM classification (ARCA activity)') {
                enrichmentMethod = cuitResult.activity ? 'CUIT database activity (keyword matching)' : 'website scraping (via CUIT search)';
                console.log(`✅ Industry inferred: ${inferredIndustryEnum} (from CUIT activity via keyword matching)`);
              }
            }
          }
        }
      }
      
      // Method 3: Search for domain online if domain is missing and CUIT search failed
      if (!inferredIndustryEnum && !companyDomain && companyName) {
        console.log(`🔍 SEARCHING FOR DOMAIN: Attempting to find domain for company "${companyName}"`);
        const foundDomain = await searchCompanyDomain(companyName);
        
        if (foundDomain) {
          console.log(`✅ DOMAIN FOUND ONLINE: ${foundDomain}`);
          const websiteContent = await fetchWebsiteContent(foundDomain);
          
          if (websiteContent) {
            inferredIndustryEnum = inferIndustryFromText(websiteContent, false);
            if (inferredIndustryEnum) {
              enrichmentMethod = 'website scraping (domain found online)';
              console.log(`✅ Industry inferred from found domain: ${inferredIndustryEnum}`);
              
              try {
                await client.crm.companies.basicApi.update(companyIdString, {
                  properties: { domain: foundDomain }
                });
                console.log(`✅ DOMAIN UPDATED: ${foundDomain}`);
              } catch (updateError) {
                console.log(`⚠️  Could not update domain field: ${updateError.message}`);
              }
            }
          }
        }
      }
      
      // Method 4: Fallback to company name analysis
      if (!inferredIndustryEnum && companyName) {
        inferredIndustryEnum = inferIndustryFromCompanyName(companyName);
        if (inferredIndustryEnum) {
          enrichmentMethod = 'company name (strong indicator)';
          console.log(`✅ Industry inferred from company name strong indicator: ${inferredIndustryEnum}`);
        } else {
          inferredIndustryEnum = inferIndustryFromText(companyName, true);
          if (inferredIndustryEnum) {
            enrichmentMethod = 'company name';
            console.log(`✅ Industry inferred from company name: ${inferredIndustryEnum}`);
          }
        }
      }
      
      // Update industria field if inference successful
      if (inferredIndustryEnum) {
        const industriaValue = mapToIndustriaField(inferredIndustryEnum);
        if (industriaValue) {
          try {
            await client.crm.companies.basicApi.update(companyIdString, {
              properties: { industria: industriaValue }
            });
            console.log(`✅ INDUSTRIA ENRICHED: Updated to "${industriaValue}" (from ${enrichmentMethod})`);
            companyIndustry = industriaValue; // Update local variable for Type inference
            newIndustria = industriaValue; // Track for notification
          } catch (updateError) {
            console.error(`❌ Failed to update industria: ${updateError.message}`);
          }
        }
      } else {
        console.log(`⚠️  Could not infer industry from available data`);
      }
      
      // Use existing ARCA activity if we didn't get one from CUIT search
      if (!arcaActivityText && existingArcaActivity) {
        arcaActivityText = existingArcaActivity;
      }
    } else {
      console.log(`✅ INDUSTRIA EXISTS: Industria field already populated: "${companyIndustry}"`);
      // Still use existing ARCA activity for reference even if industria was already populated
      if (existingArcaActivity) {
        arcaActivityText = existingArcaActivity;
      }
    }
    
    // ========================================================================
    // ARCA ACTIVITY ENRICHMENT: Always try to populate ARCA activity field if missing
    // (even if industria is already populated)
    // ========================================================================
    const isArcaActivityMissing = !existingArcaActivity || 
                                   existingArcaActivity.trim() === '' ||
                                   existingArcaActivity.trim() === 'null' ||
                                   existingArcaActivity.trim() === 'undefined';
    
    if (isArcaActivityMissing && companyCuit && companyCuit.trim() !== '') {
      console.log(`🔍 ARCA ACTIVITY ENRICHMENT: ARCA activity field is missing - attempting CUIT search`);
      console.log(`   CUIT: ${companyCuit}`);
      
      if (typeof exports._cuitFetchTested === 'undefined') {
        exports._cuitFetchTested = true;
        const fetchWorks = await testFetchAvailability();
        if (!fetchWorks) {
          console.log(`⚠️  ARCA ACTIVITY ENRICHMENT: fetch() may not work in this environment`);
        }
      }
      
      const cuitResultForArca = await searchCompanyByCUIT(companyCuit, companyName);
      
      if (cuitResultForArca && cuitResultForArca.activity) {
        console.log(`✅ ARCA ACTIVITY FOUND: Activity text found from CUIT search`);
        console.log(`   Activity: "${cuitResultForArca.activity.substring(0, 80)}${cuitResultForArca.activity.length > 80 ? '...' : ''}"`);
        
        // Clean activity text (same logic as in enrichment block)
        let cleanActivity = cuitResultForArca.activity;
        const administrativePatterns = [
          /buscar por actividad/i,
          /ganancias/i,
          /iva/i,
          /monotributo/i,
          /inscripto/i,
          /integra/i,
          /empleador/i,
          /si esta persona/i
        ];
        
        for (const pattern of administrativePatterns) {
          const match = cleanActivity.match(pattern);
          if (match && match.index) {
            cleanActivity = cleanActivity.substring(0, match.index).trim();
            break;
          }
        }
        
        cleanActivity = cleanActivity.replace(/[.,;:\s]+$/g, '').trim();
        
        // Update arcaActivityText for potential notification
        arcaActivityText = cleanActivity;
        
        // Save cleaned activity text to HubSpot field
        try {
          await client.crm.companies.basicApi.update(companyIdString, {
            properties: {
              actividad_de_la_compania_segun_arca: cleanActivity
            }
          });
          console.log(`✅ ARCA ACTIVITY SAVED: Cleaned activity text saved to HubSpot field`);
          console.log(`   Saved: "${cleanActivity.substring(0, 80)}${cleanActivity.length > 80 ? '...' : ''}"`);
          
          // Mark that ARCA activity was enriched (separate from industria enrichment)
          arcaActivityWasEnriched = true;
          // If industria was already populated, note the enrichment method
          if (isIndustriaPopulated && !newIndustria) {
            enrichmentMethod = 'ARCA activity enrichment (industria already existed)';
          }
        } catch (updateError) {
          console.log(`⚠️  Could not update actividad_de_la_compania_segun_arca field: ${updateError.message}`);
        }
      } else {
        console.log(`⚠️  ARCA ACTIVITY ENRICHMENT: No activity found for CUIT ${companyCuit}`);
      }
    } else if (isArcaActivityMissing) {
      console.log(`⚠️  ARCA ACTIVITY ENRICHMENT: Cannot search - CUIT is missing or invalid`);
    } else {
      console.log(`✅ ARCA ACTIVITY EXISTS: ARCA activity field already populated`);
      if (!arcaActivityText && existingArcaActivity) {
        arcaActivityText = existingArcaActivity;
      }
    }

    // ========================================================================
    // TYPE FIELD INFERENCE: Auto-populate Type based on Industry if Type is null
    // ========================================================================
    const originalType = currentCompanyType || 'NULL';
    let inferredType = null;
    let typeWasInferred = false;
    let typeMatchType = null;
    
    if (!currentCompanyType || currentCompanyType.trim() === '') {
      console.log(`🔍 TYPE INFERENCE: Company type is NULL/EMPTY - checking industry for inference`);
      
      if (companyIndustry && companyIndustry.trim() !== '') {
        const industryTrimmed = companyIndustry.trim();
        const industryLower = industryTrimmed.toLowerCase();
        
        const exactAccountantIndustry = 'Contabilidad, impuestos, legales';
        const isExactMatch = industryTrimmed === exactAccountantIndustry;
        
        const accountantIndustryPatterns = [
          'contabilidad', 'impuestos', 'legales', 'accounting',
          'legal_services', 'legal services', 'servicios contables',
          'servicio contable', 'tax', 'fiscal'
        ];
        
        const isPatternMatch = accountantIndustryPatterns.some(pattern => 
          industryLower.includes(pattern)
        );
        
        const isAccountantIndustry = isExactMatch || isPatternMatch;
        inferredType = isAccountantIndustry ? 'Cuenta Contador' : 'Cuenta Pyme';
        typeMatchType = isExactMatch ? 'exact match' : 'pattern match';
        typeWasInferred = true;
        
        try {
          await client.crm.companies.basicApi.update(companyIdString, {
            properties: { type: inferredType }
          });
          console.log(`✅ TYPE SET: Company type updated to "${inferredType}" based on industry "${companyIndustry}" (${typeMatchType})`);
        } catch (updateError) {
          console.error(`❌ TYPE UPDATE FAILED: ${updateError.message}`);
          typeWasInferred = false; // Mark as not inferred if update failed
        }
      } else {
        console.log(`⚠️ TYPE INFERENCE: Industry is also NULL/EMPTY - cannot infer type`);
      }
    } else {
      console.log(`✅ TYPE EXISTS: Company type is already set to "${currentCompanyType}"`);
    }

    // ========================================================================
    // STEP 4: SENDING SLACK NOTIFICATIONS
    // ========================================================================
    // Create notification if industry was enriched OR ARCA activity was enriched
    let slackNotification = null;
    
    if (newIndustria || arcaActivityWasEnriched) {
      console.log('📢 STEP 4: SENDING SLACK NOTIFICATION');
      console.log('-'.repeat(50));
      
      // Determine notification title and message based on what was enriched
      let notificationTitle;
      let notificationMessage;
      
      if (newIndustria && arcaActivityWasEnriched) {
        // Both industria and ARCA activity were enriched
        notificationTitle = typeWasInferred && inferredType
          ? `✅ Company Industry, Type & ARCA Activity Auto-Populated`
          : `✅ Company Industry & ARCA Activity Auto-Populated`;
        notificationMessage = typeWasInferred && inferredType
          ? `Company "${companyName}" had NULL industria → inferred "${newIndustria}" (method: ${enrichmentMethod}) and Type → "${inferredType}" + ARCA activity enriched`
          : `Company "${companyName}" had NULL industria → inferred "${newIndustria}" (method: ${enrichmentMethod}) + ARCA activity enriched`;
      } else if (newIndustria) {
        // Only industria was enriched
        notificationTitle = typeWasInferred && inferredType
          ? `✅ Company Industry & Type Auto-Populated`
          : `✅ Company Industry Auto-Populated`;
        notificationMessage = typeWasInferred && inferredType
          ? `Company "${companyName}" had NULL industria → inferred "${newIndustria}" (method: ${enrichmentMethod}) and Type → "${inferredType}"`
          : `Company "${companyName}" had NULL industria → inferred "${newIndustria}" (method: ${enrichmentMethod})`;
      } else if (arcaActivityWasEnriched) {
        // Only ARCA activity was enriched (industria already existed)
        notificationTitle = `✅ Company ARCA Activity Auto-Populated`;
        notificationMessage = `Company "${companyName}" had missing ARCA activity → enriched from CUIT search (industria already exists: "${companyIndustry}")`;
      }
      
      slackNotification = {
        type: 'success',
        title: notificationTitle,
        message: notificationMessage,
        details: {
          companyId: companyIdString,
          companyName: companyName,
          companyOwnerName: companyOwnerName,
          oldIndustria: originalIndustria,
          newIndustria: newIndustria || null, // Keep as null if not changed, so notification can detect no change
          industriaWasChanged: !!newIndustria, // Track if industria actually changed
          inferredIndustryEnum: inferredIndustryEnum,
          enrichmentMethod: enrichmentMethod || 'ARCA activity enrichment',
          arcaActivityText: arcaActivityText || 'N/A',
          llmReasoning: llmReasoning || null,
          domain: companyDomain || 'N/A',
          cuit: companyCuit || 'N/A',
          oldType: originalType,
          newType: inferredType || originalType,
          typeWasInferred: typeWasInferred,
          typeMatchType: typeMatchType,
          changeReason: newIndustria 
            ? `Auto-populated industria from ${enrichmentMethod}${arcaActivityText ? `: "${arcaActivityText.substring(0, 100)}${arcaActivityText.length > 100 ? '...' : ''}"` : ''}`
            : `Auto-populated ARCA activity from CUIT search${arcaActivityText ? `: "${arcaActivityText.substring(0, 100)}${arcaActivityText.length > 100 ? '...' : ''}"` : ''}`,
          arcaActivityWasEnriched: arcaActivityWasEnriched || false
        }
      };
      
      try {
        console.log(`📤 Sending notification: ${slackNotification.type} - ${slackNotification.title}`);
        await sendSlackNotification(slackNotification);
        console.log(`✅ Slack notification sent successfully`);
      } catch (slackError) {
        console.error(`❌ Slack notification failed:`, slackError.message);
        console.error(`🔍 Slack error details:`, slackError);
        // Don't fail the entire workflow if Slack fails
      }
      
      console.log('✅ STEP 4 COMPLETE');
    } else {
      console.log('📢 STEP 4: SKIPPED (No enrichment occurred)');
    }

    console.log('='.repeat(80));
    console.log('✅ INDUSTRY ENRICHMENT WORKFLOW COMPLETED');
    console.log('='.repeat(80));
    
    callback(null, 'Success');

  } catch (err) {
    console.error('=== ERROR OCCURRED ===');
    console.error('Error type:', err.constructor.name);
    console.error('Error message:', err.message);
    console.error('Error stack:', err.stack);
    callback(err);
  }
};
