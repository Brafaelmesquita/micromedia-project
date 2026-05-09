Micromedia OOH Audience Analytics Dashboard
Interactive dashboard for analysing audience data across Micromedia Ireland's digital Out-of-Home (OOH) billboard network.
Data
Provided monthly by Locomizer as CSV exports:

Footfall — audience volume and movement profile per screen
Demographics — age and gender distribution per screen
Brand Affinity — affinity index for brand/POI categories per screen


Raw data files are not version-controlled (client confidential).

Project Structure
micromedia-project/
├── data/
│   ├── raw/          ← Original CSVs (not versioned)
│   └── processed/    ← Cleaned outputs for Power BI
├── scripts/
│   ├── 00_explore_files.py
│   ├── 01_clean_site_list.py
│   ├── 02_clean_footfall.py
│   ├── 03_clean_demographics.py
│   └── 04_clean_brand_affinity.py
├── requirements.txt
└── README.md
Setup
bashpython -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
Script Execution Order
bashpython scripts/00_explore_files.py      # Inspect source files
python scripts/01_clean_site_list.py    # Generate master screen list
python scripts/02_clean_footfall.py     # Clean footfall data
python scripts/03_clean_demographics.py # Clean demographics data
python scripts/04_clean_brand_affinity.py # Clean brand affinity data