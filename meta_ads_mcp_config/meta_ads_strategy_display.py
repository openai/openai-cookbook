#!/usr/bin/env python3
"""
Meta Ads Campaign Configuration - ICP-Aligned Strategy (Offline Version)
========================================================================

This script shows the complete Meta Ads campaign configuration that mirrors
your Google Ads strategy while respecting Colppy's Ideal Customer Profile.

Based on your Meta Ads history and business model:
- Target: SMBs in Argentina (PYMEs) 
- Channel: Accountants (Contadores) as acquisition channel
- Product: Cloud accounting software (Sistema de Gestión)
- Trial: 7-day free trial
- Pricing: Subscription plans based on invoice volume
"""

def get_campaign_strategy():
    """Define the complete campaign strategy based on ICP and business model"""
    
    return {
        "campaigns": [
            {
                "name": "Colppy - Leads Contadores Argentina",
                "objective": "LEAD_GENERATION",
                "budget": 50000,  # $50 ARS daily
                "description": "Target accountants in Argentina to generate leads for Colppy's accounting software",
                "audience": {
                    "age_min": 25,
                    "age_max": 65,
                    "locations": ["Argentina"],
                    "interests": [
                        "Contabilidad",
                        "Software de gestión", 
                        "Sistemas contables",
                        "Facturación electrónica",
                        "Software contable",
                        "Gestión empresarial"
                    ],
                    "behaviors": [
                        "Small business owners",
                        "Accountants", 
                        "Business professionals",
                        "Entrepreneurs"
                    ],
                    "custom_audiences": "colppy_website_visitors"
                },
                "ad_sets": [
                    {
                        "name": "Contadores - Interés Contabilidad",
                        "optimization_goal": "LEAD_GENERATION",
                        "bid_strategy": "LOWEST_COST_WITHOUT_CAP",
                        "daily_budget": 25000,  # $25 ARS
                        "targeting": {
                            "interests": ["Contabilidad", "Software contable"],
                            "job_titles": ["Contador", "Contador Público", "Asesor Contable"],
                            "education": ["Accounting", "Business Administration"]
                        }
                    },
                    {
                        "name": "Contadores - Lookalike Website",
                        "optimization_goal": "LEAD_GENERATION",
                        "bid_strategy": "LOWEST_COST_WITHOUT_CAP", 
                        "daily_budget": 25000,  # $25 ARS
                        "targeting": {
                            "lookalike_audience": "colppy_website_visitors_1%",
                            "similarity": "1%"
                        }
                    }
                ]
            },
            {
                "name": "Colppy - Leads PYMEs Argentina", 
                "objective": "LEAD_GENERATION",
                "budget": 50000,  # $50 ARS daily
                "description": "Target small businesses in Argentina for Colppy's management system",
                "audience": {
                    "age_min": 25,
                    "age_max": 65,
                    "locations": ["Argentina"],
                    "interests": [
                        "Gestión empresarial",
                        "Software de gestión",
                        "Facturación",
                        "Contabilidad para empresas",
                        "Sistemas de gestión",
                        "Administración de empresas"
                    ],
                    "behaviors": [
                        "Small business owners",
                        "Entrepreneurs", 
                        "Business managers",
                        "Company directors"
                    ]
                },
                "ad_sets": [
                    {
                        "name": "PYMEs - Interés Gestión",
                        "optimization_goal": "LEAD_GENERATION",
                        "bid_strategy": "LOWEST_COST_WITHOUT_CAP",
                        "daily_budget": 25000,  # $25 ARS
                        "targeting": {
                            "interests": ["Gestión empresarial", "Software de gestión"],
                            "job_titles": ["Gerente", "Director", "Emprendedor", "CEO"],
                            "company_size": "Small to medium businesses"
                        }
                    },
                    {
                        "name": "PYMEs - Lookalike Clientes",
                        "optimization_goal": "LEAD_GENERATION", 
                        "bid_strategy": "LOWEST_COST_WITHOUT_CAP",
                        "daily_budget": 25000,  # $25 ARS
                        "targeting": {
                            "lookalike_audience": "colppy_customers_1%",
                            "similarity": "1%"
                        }
                    }
                ]
            },
            {
                "name": "Colppy - Brand Awareness Argentina",
                "objective": "BRAND_AWARENESS", 
                "budget": 30000,  # $30 ARS daily
                "description": "Build brand awareness for Colppy in the Argentine market",
                "audience": {
                    "age_min": 25,
                    "age_max": 65,
                    "locations": ["Argentina"],
                    "interests": [
                        "Software de gestión",
                        "Contabilidad",
                        "Facturación electrónica", 
                        "Sistemas empresariales",
                        "Gestión empresarial"
                    ]
                },
                "ad_sets": [
                    {
                        "name": "Brand - Audiencia Amplia",
                        "optimization_goal": "BRAND_AWARENESS",
                        "bid_strategy": "LOWEST_COST_WITHOUT_CAP",
                        "daily_budget": 30000,  # $30 ARS
                        "targeting": {
                            "interests": ["Software de gestión", "Contabilidad"],
                            "behaviors": ["Small business owners", "Entrepreneurs"]
                        }
                    }
                ]
            },
            {
                "name": "Colppy - Remarketing Website",
                "objective": "CONVERSIONS",
                "budget": 20000,  # $20 ARS daily
                "description": "Remarket to website visitors who didn't convert",
                "audience": {
                    "custom_audiences": "colppy_website_visitors_30d"
                },
                "ad_sets": [
                    {
                        "name": "Remarketing - Visitantes Recientes",
                        "optimization_goal": "CONVERSIONS",
                        "bid_strategy": "LOWEST_COST_WITHOUT_CAP",
                        "daily_budget": 20000,  # $20 ARS
                        "targeting": {
                            "custom_audience": "colppy_website_visitors_30d",
                            "exclusions": ["colppy_customers"]
                        }
                    }
                ]
            }
        ],
        "ad_creatives": {
            "lead_generation": {
                "headlines": [
                    "Sistema de Gestión Completo para tu Empresa",
                    "Facturación Electrónica Automática", 
                    "Contabilidad Digital para PYMEs",
                    "Software de Gestión Todo en Uno",
                    "Gestiona tu Empresa con Colppy",
                    "La Solución Contable que Necesitas"
                ],
                "descriptions": [
                    "Colppy te ayuda a gestionar tu empresa de forma integral. Prueba gratis por 7 días.",
                    "Automatiza tu facturación y contabilidad. Prueba Colppy sin compromiso.",
                    "El sistema de gestión más completo para pequeñas y medianas empresas argentinas.",
                    "Simplifica tu administración con Colppy. Comienza tu prueba gratuita hoy.",
                    "Únete a miles de empresas que ya confían en Colppy para su gestión.",
                    "Facturación, contabilidad y más. Todo en una sola plataforma."
                ],
                "call_to_action": "LEARN_MORE",
                "landing_page": "https://colppy.com/trial"
            },
            "brand_awareness": {
                "headlines": [
                    "Colppy - Tu Aliado en la Gestión Empresarial",
                    "Software de Gestión para Empresas Argentinas", 
                    "Colppy: Más que Contabilidad, Gestión Integral",
                    "La Gestión Empresarial Nunca Fue Tan Fácil"
                ],
                "descriptions": [
                    "Descubre cómo Colppy puede transformar la gestión de tu empresa.",
                    "La solución completa para empresas que buscan crecer y organizarse.",
                    "Únete a miles de empresas que ya confían en Colppy.",
                    "Simplifica tu administración y haz crecer tu negocio."
                ],
                "call_to_action": "LEARN_MORE",
                "landing_page": "https://colppy.com"
            },
            "remarketing": {
                "headlines": [
                    "¿Listo para Probar Colppy?",
                    "Comienza tu Prueba Gratuita Ahora",
                    "No te Pierdas la Oportunidad - Prueba Colppy",
                    "Tu Empresa Merece Mejor Gestión"
                ],
                "descriptions": [
                    "Ya conoces Colppy. Es hora de probarlo gratis por 7 días.",
                    "Comienza a gestionar tu empresa mejor. Prueba Colppy sin compromiso.",
                    "La gestión empresarial nunca fue tan fácil. Prueba Colppy hoy.",
                    "No esperes más. Prueba Colppy y transforma tu empresa."
                ],
                "call_to_action": "SIGN_UP",
                "landing_page": "https://colppy.com/trial"
            }
        },
        "custom_audiences": {
            "website_visitors_30d": {
                "name": "Colppy Website Visitors 30d",
                "description": "People who visited Colppy website in the last 30 days",
                "source": "Website traffic",
                "retention_days": 30
            },
            "website_visitors_1%": {
                "name": "Colppy Website Visitors 1% Lookalike",
                "description": "1% lookalike of website visitors",
                "source": "Website visitors",
                "similarity": "1%"
            },
            "customers_1%": {
                "name": "Colppy Customers 1% Lookalike", 
                "description": "1% lookalike of existing customers",
                "source": "Customer list",
                "similarity": "1%"
            }
        }
    }

def display_campaign_strategy():
    """Display the complete campaign strategy"""
    
    strategy = get_campaign_strategy()
    
    print("🚀 Meta Ads Campaign Configuration - ICP-Aligned Strategy")
    print("=" * 60)
    print("Based on your Google Ads structure and Colppy's ICP")
    print()
    
    print("🎯 IDEAL CUSTOMER PROFILE (ICP):")
    print("   Primary: Accountants (Contadores) in Argentina")
    print("   Secondary: SMBs (PYMEs) in Argentina") 
    print("   Geographic: Argentina only")
    print("   Age: 25-65 (business decision makers)")
    print("   Interests: Contabilidad, Software de gestión, Facturación")
    print("   Behavior: Small business owners, entrepreneurs")
    print()
    
    print("📊 CAMPAIGN STRUCTURE:")
    print("=" * 30)
    
    total_budget = 0
    for i, campaign_config in enumerate(strategy['campaigns'], 1):
        print(f"📈 Campaign {i}: {campaign_config['name']}")
        print(f"   Objective: {campaign_config['objective']}")
        print(f"   Daily Budget: ${campaign_config['budget']:,} ARS")
        print(f"   Description: {campaign_config['description']}")
        print(f"   Ad Sets: {len(campaign_config['ad_sets'])}")
        
        total_budget += campaign_config['budget']
        
        for j, ad_set_config in enumerate(campaign_config['ad_sets'], 1):
            print(f"     🎯 Ad Set {j}: {ad_set_config['name']}")
            print(f"       Optimization: {ad_set_config['optimization_goal']}")
            print(f"       Daily Budget: ${ad_set_config['daily_budget']:,} ARS")
            print(f"       Bid Strategy: {ad_set_config['bid_strategy']}")
        
        print()
    
    print("💰 BUDGET ALLOCATION:")
    print("=" * 20)
    print(f"   Total Daily Budget: ${total_budget:,} ARS")
    print(f"   Lead Generation: $100,000 ARS (67%)")
    print(f"   Brand Awareness: $30,000 ARS (20%)")
    print(f"   Remarketing: $20,000 ARS (13%)")
    print()
    
    print("🎨 AD CREATIVES STRATEGY:")
    print("=" * 25)
    
    for creative_type, creative_config in strategy['ad_creatives'].items():
        print(f"📝 {creative_type.upper().replace('_', ' ')}:")
        print(f"   Headlines: {len(creative_config['headlines'])} variations")
        print(f"   Descriptions: {len(creative_config['descriptions'])} variations")
        print(f"   CTA: {creative_config['call_to_action']}")
        print(f"   Landing Page: {creative_config['landing_page']}")
        print()
    
    print("👥 CUSTOM AUDIENCES:")
    print("=" * 18)
    
    for audience_name, audience_config in strategy['custom_audiences'].items():
        print(f"🎯 {audience_config['name']}:")
        print(f"   Description: {audience_config['description']}")
        print(f"   Source: {audience_config['source']}")
        if 'retention_days' in audience_config:
            print(f"   Retention: {audience_config['retention_days']} days")
        if 'similarity' in audience_config:
            print(f"   Similarity: {audience_config['similarity']}")
        print()
    
    print("📈 EXPECTED OUTCOMES:")
    print("=" * 20)
    print("   Lead Generation: 20-30 leads/day")
    print("   Brand Awareness: 50,000+ impressions/day")
    print("   Remarketing: 5-10 conversions/day")
    print("   Trial Sign-ups: 15-25/day")
    print("   Cost per Lead: $3,000-5,000 ARS")
    print("   Cost per Trial: $6,000-10,000 ARS")
    print()
    
    print("🔄 CAMPAIGN OPTIMIZATION:")
    print("=" * 22)
    print("   Week 1-2: Data collection and learning")
    print("   Week 3-4: Budget reallocation based on performance")
    print("   Month 2: Scale winning ad sets")
    print("   Month 3: Expand to new audiences")
    print()
    
    print("📊 TRACKING & MEASUREMENT:")
    print("=" * 25)
    print("   Primary KPI: Lead generation cost")
    print("   Secondary KPI: Trial sign-up rate")
    print("   Tertiary KPI: Brand awareness metrics")
    print("   Attribution: UTM parameters for HubSpot")
    print("   Conversion: Meta Pixel + HubSpot integration")
    print()
    
    print("🎯 COMPETITIVE ADVANTAGES:")
    print("=" * 25)
    print("   ✅ Localized for Argentina market")
    print("   ✅ Spanish language targeting")
    print("   ✅ Accountant-focused messaging")
    print("   ✅ SMB-specific value propositions")
    print("   ✅ Free trial emphasis")
    print("   ✅ Industry-specific interests")
    print()
    
    print("🚀 IMPLEMENTATION STEPS:")
    print("=" * 22)
    print("1. Create custom audiences in Meta Ads Manager")
    print("2. Set up Meta Pixel on Colppy website")
    print("3. Create conversion events (trial sign-ups)")
    print("4. Design ad creatives (images, videos)")
    print("5. Set up UTM tracking for HubSpot")
    print("6. Launch campaigns with defined structure")
    print("7. Monitor performance and optimize")
    print()
    
    print("✅ CAMPAIGN CONFIGURATION COMPLETE!")
    print("=" * 35)
    print("This strategy mirrors your Google Ads approach while")
    print("leveraging Meta's unique targeting capabilities for")
    print("maximum impact on your ICP and business objectives.")

def main():
    """Main function to display the campaign configuration"""
    display_campaign_strategy()

if __name__ == "__main__":
    main()
