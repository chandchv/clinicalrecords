#!/usr/bin/env python3
"""
Download offline assets for ClinicalRecordsService

This script downloads external CSS, JS, and font files to make the ClinicalRecordsService
work offline without CDN dependencies.
"""

import os
import requests
import json
from pathlib import Path

# Configuration
STATIC_DIR = Path("clinical_records/static/clinical_records")
ASSETS = {
    "css": {
        "tailwind": {
            "url": "https://cdn.tailwindcss.com",
            "filename": "tailwind.min.css"
        }
    },
    "js": {
        "alpine": {
            "url": "https://unpkg.com/alpinejs@3.x.x/dist/cdn.min.js",
            "filename": "alpine.min.js"
        },
        "htmx": {
            "url": "https://unpkg.com/htmx.org@1.9.10/dist/htmx.min.js",
            "filename": "htmx.min.js"
        },
        "chart": {
            "url": "https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.min.js",
            "filename": "chart.min.js"
        }
    },
    "webfonts": {
        "fa-solid-900": {
            "url": "https://use.fontawesome.com/releases/v6.4.0/webfonts/fa-solid-900.woff2",
            "filename": "fa-solid-900.woff2"
        },
        "fa-solid-900-ttf": {
            "url": "https://use.fontawesome.com/releases/v6.4.0/webfonts/fa-solid-900.ttf",
            "filename": "fa-solid-900.ttf"
        },
        "fa-regular-400": {
            "url": "https://use.fontawesome.com/releases/v6.4.0/webfonts/fa-regular-400.woff2",
            "filename": "fa-regular-400.woff2"
        },
        "fa-regular-400-ttf": {
            "url": "https://use.fontawesome.com/releases/v6.4.0/webfonts/fa-regular-400.ttf",
            "filename": "fa-regular-400.ttf"
        },
        "fa-brands-400": {
            "url": "https://use.fontawesome.com/releases/v6.4.0/webfonts/fa-brands-400.woff2",
            "filename": "fa-brands-400.woff2"
        },
        "fa-brands-400-ttf": {
            "url": "https://use.fontawesome.com/releases/v6.4.0/webfonts/fa-brands-400.ttf",
            "filename": "fa-brands-400.ttf"
        }
    }
}

def create_directories():
    """Create necessary directories"""
    directories = [
        STATIC_DIR / "css",
        STATIC_DIR / "js", 
        STATIC_DIR / "webfonts",
        STATIC_DIR / "images",
        STATIC_DIR / "icons",
        STATIC_DIR / "locales"
    ]
    
    for directory in directories:
        directory.mkdir(parents=True, exist_ok=True)
        print(f"✓ Created directory: {directory}")

def download_file(url, filepath):
    """Download a file from URL to filepath"""
    try:
        print(f"Downloading {url}...")
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        
        with open(filepath, 'wb') as f:
            f.write(response.content)
        
        print(f"✓ Downloaded: {filepath}")
        return True
    except Exception as e:
        print(f"✗ Failed to download {url}: {e}")
        return False

def create_fontawesome_css():
    """Create Font Awesome CSS file"""
    css_content = """/* Font Awesome 6.4.0 */
@font-face {
  font-family: "Font Awesome 6 Free";
  font-style: normal;
  font-weight: 900;
  font-display: block;
  src: url("../webfonts/fa-solid-900.woff2") format("woff2"),
       url("../webfonts/fa-solid-900.ttf") format("truetype");
}

@font-face {
  font-family: "Font Awesome 6 Free";
  font-style: normal;
  font-weight: 400;
  font-display: block;
  src: url("../webfonts/fa-regular-400.woff2") format("woff2"),
       url("../webfonts/fa-regular-400.ttf") format("truetype");
}

@font-face {
  font-family: "Font Awesome 6 Brands";
  font-style: normal;
  font-weight: 400;
  font-display: block;
  src: url("../webfonts/fa-brands-400.woff2") format("woff2"),
       url("../webfonts/fa-brands-400.ttf") format("truetype");
}

.fa,
.fas {
  font-family: "Font Awesome 6 Free";
  font-weight: 900;
}

.far {
  font-family: "Font Awesome 6 Free";
  font-weight: 400;
}

.fab {
  font-family: "Font Awesome 6 Brands";
  font-weight: 400;
}

/* Common icons */
.fa-user::before { content: "\\f007"; }
.fa-sign-out-alt::before { content: "\\f2f5"; }
.fa-home::before { content: "\\f015"; }
.fa-dashboard::before { content: "\\f3fd"; }
.fa-file-medical::before { content: "\\f477"; }
.fa-chart-line::before { content: "\\f201"; }
.fa-upload::before { content: "\\f093"; }
.fa-cog::before { content: "\\f013"; }
.fa-search::before { content: "\\f002"; }
.fa-plus::before { content: "\\f067"; }
.fa-edit::before { content: "\\f044"; }
.fa-trash::before { content: "\\f1f8"; }
.fa-eye::before { content: "\\f06e"; }
.fa-download::before { content: "\\f019"; }
.fa-share::before { content: "\\f064"; }
.fa-lock::before { content: "\\f023"; }
.fa-unlock::before { content: "\\f09c"; }
.fa-check::before { content: "\\f00c"; }
.fa-times::before { content: "\\f00d"; }
.fa-exclamation-triangle::before { content: "\\f071"; }
.fa-info-circle::before { content: "\\f05a"; }
.fa-calendar::before { content: "\\f133"; }
.fa-clock::before { content: "\\f017"; }
.fa-user-md::before { content: "\\f82c"; }
.fa-user-injured::before { content: "\\f728"; }
.fa-hospital::before { content: "\\f0f8"; }
.fa-stethoscope::before { content: "\\f0f1"; }
.fa-pills::before { content: "\\f484"; }
.fa-heartbeat::before { content: "\\f21e"; }
.fa-thermometer-half::before { content: "\\f2c9"; }
.fa-weight::before { content: "\\f496"; }
.fa-ruler::before { content: "\\f545"; }
.fa-tint::before { content: "\\f043"; }
.fa-heart::before { content: "\\f004"; }
.fa-lungs::before { content: "\\f604"; }
.fa-brain::before { content: "\\f5dc"; }
.fa-tooth::before { content: "\\f5c9"; }
.fa-eye::before { content: "\\f06e"; }
.fa-ear::before { content: "\\f5f0"; }
.fa-hand-holding-medical::before { content: "\\f95c"; }
.fa-shield-virus::before { content: "\\f96c"; }
.fa-virus::before { content: "\\f974"; }
.fa-bacteria::before { content: "\\f959"; }
.fa-dna::before { content: "\\f471"; }
.fa-microscope::before { content: "\\f610"; }
.fa-flask::before { content: "\\f0c3"; }
.fa-prescription-bottle::before { content: "\\f485"; }
.fa-syringe::before { content: "\\f48e"; }
.fa-band-aid::before { content: "\\f462"; }
.fa-ambulance::before { content: "\\f0f9"; }
.fa-helicopter::before { content: "\\f533"; }
.fa-plane::before { content: "\\f072"; }
.fa-car::before { content: "\\f1b9"; }
.fa-walking::before { content: "\\f554"; }
.fa-wheelchair::before { content: "\\f193"; }
.fa-procedures::before { content: "\\f487"; }
.fa-user-nurse::before { content: "\\f82f"; }
.fa-user-doctor::before { content: "\\f82c"; }
.fa-user-graduate::before { content: "\\f501"; }
.fa-user-tie::before { content: "\\f508"; }
.fa-user-shield::before { content: "\\f505"; }
.fa-user-secret::before { content: "\\f21b"; }
.fa-user-check::before { content: "\\f4fc"; }
.fa-user-times::before { content: "\\f235"; }
.fa-user-plus::before { content: "\\f234"; }
.fa-user-minus::before { content: "\\f503"; }
.fa-user-edit::before { content: "\\f4ff"; }
.fa-user-cog::before { content: "\\f4fe"; }
.fa-user-clock::before { content: "\\f4fd"; }
.fa-user-lock::before { content: "\\f502"; }
.fa-user-unlock::before { content: "\\f506"; }
.fa-user-tag::before { content: "\\f507"; }
.fa-user-slash::before { content: "\\f506"; }
.fa-user-graduate::before { content: "\\f501"; }
.fa-user-friends::before { content: "\\f500"; }
.fa-users::before { content: "\\f0c0"; }
.fa-user-friends::before { content: "\\f500"; }
.fa-user-plus::before { content: "\\f234"; }
.fa-user-minus::before { content: "\\f503"; }
.fa-user-edit::before { content: "\\f4ff"; }
.fa-user-cog::before { content: "\\f4fe"; }
.fa-user-clock::before { content: "\\f4fd"; }
.fa-user-lock::before { content: "\\f502"; }
.fa-user-unlock::before { content: "\\f506"; }
.fa-user-tag::before { content: "\\f507"; }
.fa-user-slash::before { content: "\\f506"; }
.fa-user-graduate::before { content: "\\f501"; }
.fa-user-friends::before { content: "\\f500"; }
.fa-users::before { content: "\\f0c0"; }
"""
    
    filepath = STATIC_DIR / "css" / "fontawesome.min.css"
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(css_content)
    print(f"✓ Created: {filepath}")

def create_custom_icons():
    """Create custom SVG icons"""
    icons = {
        "heart.svg": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor">
  <path d="M12 21.35l-1.45-1.32C5.4 15.36 2 12.28 2 8.5 2 5.42 4.42 3 7.5 3c1.74 0 3.41.81 4.5 2.09C13.09 3.81 14.76 3 16.5 3 19.58 3 22 5.42 22 8.5c0 3.78-3.4 6.86-8.55 11.54L12 21.35z"/>
</svg>""",
        "hospital.svg": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor">
  <path d="M19 3H5c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h14c1.1 0 2-.9 2-2V5c0-1.1-.9-2-2-2zm-7 14h-2v-2h2v2zm0-4h-2V7h2v6z"/>
</svg>""",
        "spinner.svg": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor">
  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" style="animation: spin 1s linear infinite;"/>
</svg>""",
        "user.svg": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor">
  <path d="M12 12c2.21 0 4-1.79 4-4s-1.79-4-4-4-4 1.79-4 4 1.79 4 4 4zm0 2c-2.67 0-8 1.34-8 4v2h16v-2c0-2.66-5.33-4-8-4z"/>
</svg>""",
        "calendar.svg": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor">
  <path d="M19 3h-1V1h-2v2H8V1H6v2H5c-1.11 0-1.99.9-1.99 2L3 19c0 1.1.89 2 2 2h14c1.1 0 2-.9 2-2V5c0-1.1-.9-2-2-2zm0 16H5V8h14v11zM7 10h5v5H7z"/>
</svg>""",
        "medicine.svg": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor">
  <path d="M17 3H7c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h10c1.1 0 2-.9 2-2V5c0-1.1-.9-2-2-2zm-5 14c-1.66 0-3-1.34-3-3s1.34-3 3-3 3 1.34 3 3-1.34 3-3 3z"/>
</svg>"""
    }
    
    for filename, content in icons.items():
        filepath = STATIC_DIR / "icons" / filename
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"✓ Created: {filepath}")

def create_translations():
    """Create basic translation files"""
    translations = {
        "en.json": {
            "welcome": "Welcome",
            "logout": "Logout",
            "dashboard": "Dashboard",
            "records": "Records",
            "analytics": "Analytics",
            "upload": "Upload",
            "admin": "Admin",
            "confirm_logout": "Confirm Logout",
            "logout_message": "Are you sure you want to log out?",
            "yes_logout": "Yes, Logout",
            "cancel": "Cancel"
        },
        "es.json": {
            "welcome": "Bienvenido",
            "logout": "Cerrar sesión",
            "dashboard": "Panel de control",
            "records": "Registros",
            "analytics": "Análisis",
            "upload": "Subir",
            "admin": "Administrador",
            "confirm_logout": "Confirmar cierre de sesión",
            "logout_message": "¿Está seguro de que desea cerrar sesión?",
            "yes_logout": "Sí, cerrar sesión",
            "cancel": "Cancelar"
        },
        "fr.json": {
            "welcome": "Bienvenue",
            "logout": "Déconnexion",
            "dashboard": "Tableau de bord",
            "records": "Enregistrements",
            "analytics": "Analyses",
            "upload": "Télécharger",
            "admin": "Administrateur",
            "confirm_logout": "Confirmer la déconnexion",
            "logout_message": "Êtes-vous sûr de vouloir vous déconnecter?",
            "yes_logout": "Oui, se déconnecter",
            "cancel": "Annuler"
        }
    }
    
    for filename, content in translations.items():
        filepath = STATIC_DIR / "locales" / filename
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(content, f, indent=2, ensure_ascii=False)
        print(f"✓ Created: {filepath}")

def main():
    """Main function to download all assets"""
    print("🚀 Starting ClinicalRecordsService offline assets download...")
    
    # Create directories
    create_directories()
    
    # Download CSS files
    print("\n📁 Downloading CSS files...")
    for name, config in ASSETS["css"].items():
        filepath = STATIC_DIR / "css" / config["filename"]
        download_file(config["url"], filepath)
    
    # Download JS files
    print("\n📁 Downloading JS files...")
    for name, config in ASSETS["js"].items():
        filepath = STATIC_DIR / "js" / config["filename"]
        download_file(config["url"], filepath)
    
    # Download webfonts
    print("\n📁 Downloading webfonts...")
    for name, config in ASSETS["webfonts"].items():
        filepath = STATIC_DIR / "webfonts" / config["filename"]
        download_file(config["url"], filepath)
    
    # Create Font Awesome CSS
    print("\n📁 Creating Font Awesome CSS...")
    create_fontawesome_css()
    
    # Create custom icons
    print("\n📁 Creating custom icons...")
    create_custom_icons()
    
    # Create translations
    print("\n📁 Creating translation files...")
    create_translations()
    
    print("\n✅ ClinicalRecordsService offline assets download completed!")
    print("\n📝 Next steps:")
    print("1. Update templates to use local static files instead of CDN")
    print("2. Run 'python manage.py collectstatic' if needed")
    print("3. Restart the ClinicalRecordsService")

if __name__ == "__main__":
    main()
