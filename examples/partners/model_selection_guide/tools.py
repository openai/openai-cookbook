"""
Mock implementations of tool functions for AI Co-Scientist.

These are simple mocks of the external tools that would be used in a real implementation.
"""

import random, logging
from typing import Dict, List, Any, Optional

# Mock database of chemical properties
MOCK_CHEMICALS = {
    "Palladium acetate": {
        "solubility": "Soluble in chloroform, slightly soluble in acetone",
        "melting_point": "205°C (decomposition)",
        "hazards": "Irritant, potential carcinogen",
        "approved_status": True,
        "cost_per_gram": 85.50
    },
    "Triphenylphosphine": {
        "solubility": "Soluble in ethanol, benzene, chloroform",
        "melting_point": "80-82°C",
        "hazards": "Irritant",
        "approved_status": True,
        "cost_per_gram": 12.75
    },
    "Triethylamine": {
        "solubility": "Miscible with water, ethanol",
        "melting_point": "-115°C",
        "boiling_point": "89°C",
        "hazards": "Flammable, corrosive",
        "approved_status": True,
        "cost_per_gram": 5.25
    },
    "Sodium borohydride": {
        "solubility": "Soluble in water, methanol",
        "melting_point": "400°C (decomposition)",
        "hazards": "Flammable, water-reactive",
        "approved_status": True,
        "cost_per_gram": 8.90
    },
    "Dimethylformamide": {
        "solubility": "Miscible with water, ethanol",
        "boiling_point": "153°C",
        "hazards": "Reproductive toxin, flammable",
        "approved_status": True,
        "cost_per_gram": 3.15
    },
    "Palladium chloride": {
        "solubility": "Slightly soluble in water, soluble in HCl",
        "melting_point": "679°C",
        "hazards": "Irritant, potential carcinogen",
        "approved_status": True,
        "cost_per_gram": 75.20
    },
    "Potassium carbonate": {
        "solubility": "Soluble in water",
        "melting_point": "891°C",
        "hazards": "Irritant",
        "approved_status": True,
        "cost_per_gram": 2.50
    },
    "Toluene": {
        "solubility": "Immiscible with water, miscible with organic solvents",
        "boiling_point": "110.6°C",
        "hazards": "Flammable, CNS depressant",
        "approved_status": True,
        "cost_per_gram": 1.75
    },
    "Methanol": {
        "solubility": "Miscible with water",
        "boiling_point": "64.7°C",
        "hazards": "Flammable, toxic",
        "approved_status": True,
        "cost_per_gram": 1.20
    },
    "XYZ-13": {
        "solubility": "Slightly soluble in organic solvents",
        "melting_point": "185-188°C",
        "hazards": "Mild irritant",
        "approved_status": True,
        "cost_per_gram": 250.00
    }
}

# Mock database of past experiment outcomes
MOCK_OUTCOMES = {
    "XYZ-13": [
        {
            "id": "exp-001",
            "catalyst": "Palladium acetate",
            "temperature": 85,
            "solvent": "Dimethylformamide",
            "yield": 62.3,
            "duration": 36,
            "notes": "Yield decreased at temperatures above 85°C."
        },
        {
            "id": "exp-002",
            "catalyst": "Palladium chloride",
            "temperature": 70,
            "solvent": "Toluene",
            "yield": 58.7,
            "duration": 42,
            "notes": "Lower temperature gave slightly lower yield but higher purity."
        },
        {
            "id": "exp-003",
            "catalyst": "Palladium acetate",
            "temperature": 90,
            "solvent": "Methanol",
            "yield": 45.2,
            "duration": 28,
            "notes": "Significant side products observed at this temperature."
        }
    ]
}

# Mock literature database
MOCK_LITERATURE = [
    {
        "title": "Palladium-Catalyzed Cross-Coupling for the Synthesis of XYZ Derivatives",
        "authors": "Smith, J.L., et al.",
        "journal": "Journal of Organic Chemistry",
        "year": 2024,
        "abstract": "Novel methods using palladium catalysts at moderate temperatures showed improved yields for XYZ-type compounds."
    },
    {
        "title": "Solvent Effects on the Yield of XYZ Compounds",
        "authors": "Johnson, M.R., et al.",
        "journal": "Chemical Communications",
        "year": 2023,
        "abstract": "Polar aprotic solvents demonstrated superior performance in the synthesis of XYZ compounds, with yields up to 70%."
    },
    {
        "title": "Temperature-Controlled Synthesis of Pharmaceutical Intermediates",
        "authors": "Rodriguez, A., et al.",
        "journal": "ACS Catalysis",
        "year": 2024,
        "abstract": "Lower temperature protocols (50-65°C) with extended reaction times showed reduced side products for sensitive compounds."
    }
]

def list_available_chemicals() -> Dict:
    """Mock function to list all available chemicals in the database."""
    logging.info(f"(Tool) List available chemicals")
    return {
        "status": "success",
        "available_chemicals": list(MOCK_CHEMICALS.keys())
    }

def chem_lookup(chemical_name: str, property: Optional[str] = None) -> Dict:
    """Mock function to look up chemical properties."""
    logging.info(f"(Tool) Chemical lookup: {chemical_name}, {property}")
    # Check if chemical exists in our mock database
    if chemical_name not in MOCK_CHEMICALS:
        similar_chemicals = [c for c in MOCK_CHEMICALS.keys() if any(word in c.lower() for word in chemical_name.lower().split())]
        return {
            "status": "not_found",
            "message": f"Chemical '{chemical_name}' not found in database.",
            "similar_chemicals": similar_chemicals if similar_chemicals else []
        }
    
    # Return specific property if requested
    if property and property in MOCK_CHEMICALS[chemical_name]:
        return {
            "status": "success",
            "chemical": chemical_name,
            "property": property,
            "value": MOCK_CHEMICALS[chemical_name][property]
        }
    
    # Return all properties
    return {
        "status": "success",
        "chemical": chemical_name,
        "properties": MOCK_CHEMICALS[chemical_name]
    }

def cost_estimator(reagents: List[Dict] = [], equipment: Optional[List[str]] = None, duration_hours: Optional[float] = None) -> Dict:
    """Mock function to estimate the cost of reagents and procedures."""
    logging.info(f"(Tool) Cost estimator: {reagents}, {equipment}, {duration_hours}")
    total_cost = 0
    reagent_costs = {}
    equipment_costs = {}
    labor_cost = 0
    
    # Calculate reagent costs
    for reagent in reagents:
        # Mock: Use defaults for missing keys instead of returning errors
        if not isinstance(reagent, dict):
            reagent = {"name": "Unknown reagent", "amount": 1, "unit": "g"}
            
        name = reagent.get("name", "XYZ-13")
        amount = reagent.get("amount", 1)  # Default to 1 if amount is missing
        unit = reagent.get("unit", "g")  # Default to grams if unit not specified
        
        # Convert units to grams for calculation
        amount_in_grams = amount
        if unit.lower() == "mg":
            amount_in_grams = amount / 1000
        elif unit.lower() == "kg":
            amount_in_grams = amount * 1000
        
        # Look up cost per gram
        cost_per_gram = MOCK_CHEMICALS.get(name, {}).get("cost_per_gram", 10.0)  # Default cost if not found
        cost = amount_in_grams * cost_per_gram
        reagent_costs[name] = cost
        total_cost += cost
    
    # Add equipment costs if provided
    if equipment:
        for item in equipment:
            # Mock equipment costs
            if "hplc" in item.lower():
                cost = 250.0
            elif "nmr" in item.lower():
                cost = 350.0
            elif "reactor" in item.lower():
                cost = 150.0
            else:
                cost = 50.0
            
            equipment_costs[item] = cost
            total_cost += cost
    
    # Add labor costs based on duration
    if duration_hours:
        labor_rate = 75.0  # Mock hourly rate
        labor_cost = duration_hours * labor_rate
        total_cost += labor_cost
    
    return {
        "status": "success",
        "total_cost": round(total_cost, 2),
        "reagent_costs": reagent_costs,
        "equipment_costs": equipment_costs,
        "labor_cost": labor_cost,
        "currency": "USD"
    }

def outcome_db(compound: str, parameter: Optional[str] = None, limit: int = 5) -> Dict:
    """Mock function to query the database of past experiment outcomes."""
    logging.info(f"(Tool) Outcome DB: {compound}, {parameter}, {limit}")
    if compound not in MOCK_OUTCOMES:
        return {
            "status": "not_found",
            "message": f"No experiments found for compound '{compound}'."
        }
    
    experiments = MOCK_OUTCOMES[compound]
    
    # Filter by parameter if provided
    if parameter:
        filtered_experiments = [exp for exp in experiments if parameter in exp]
        if not filtered_experiments:
            return {
                "status": "parameter_not_found",
                "message": f"No experiments with parameter '{parameter}' found for compound '{compound}'."
            }
        experiments = filtered_experiments
    
    # Limit the number of results
    experiments = experiments[:limit]
    
    return {
        "status": "success",
        "compound": compound,
        "experiments": experiments,
        "count": len(experiments)
    }

def literature_search(query: str, filter: Optional[str] = None, limit: int = 3) -> Dict:
    """Mock function to search scientific literature for relevant information."""
    logging.info(f"(Tool) Literature search: {query}, {filter}, {limit}")
    # Simple keyword matching for demo purposes
    keywords = [word.lower() for word in query.split()]
    
    matched_literature = []
    for paper in MOCK_LITERATURE:
        # Check if any keyword appears in title or abstract
        title_lower = paper["title"].lower()
        abstract_lower = paper["abstract"].lower()
        
        if any(keyword in title_lower or keyword in abstract_lower for keyword in keywords):
            matched_literature.append(paper)
    
    # Apply filter if provided
    if filter:
        filter_year_match = None
        # Try to extract year from filter
        import re
        year_match = re.search(r'20\d\d', filter)
        if year_match:
            filter_year = int(year_match.group())
            matched_literature = [paper for paper in matched_literature if paper["year"] == filter_year]
        
        # Filter by journal if mentioned
        filter_lower = filter.lower()
        journal_matches = [paper for paper in matched_literature if filter_lower in paper["journal"].lower()]
        if journal_matches:
            matched_literature = journal_matches
    
    # Limit the number of results
    matched_literature = matched_literature[:limit]
    
    return {
        "status": "success",
        "query": query,
        "filter": filter,
        "results": matched_literature,
        "count": len(matched_literature)
    }