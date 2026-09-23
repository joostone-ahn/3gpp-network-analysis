# 3GPP Network Analysis Pipeline

A data pipeline for collecting, parsing, and analyzing 3GPP TDoc (Technical Document) data to build company collaboration networks and Work Item association networks.

## Overview

3GPP (3rd Generation Partnership Project) is an international standards organization for mobile telecommunications. This pipeline collects TDoc lists from the 3GPP FTP server and analyzes inter-company collaboration relationships and Work Item associations using network analysis techniques.

### Key Features

- **Data Collection**: Automatic download of TDoc list xlsx files from 3GPP FTP server
- **Parsing & Preprocessing**: TDoc metadata parsing, column normalization, date range filtering
- **Network Construction**: Company collaboration network and Work Item association network edge list generation
- **Analysis**: Centrality analysis, community detection, temporal analysis
- **Visualization**: Streamlit-based dashboard

## Pipeline Architecture

```
+-------------+     +-------------+     +---------------+     +-------------+
|  Collector  | --> |   Parser    | --> | Preprocessor  | --> |   Builder   |
| (FTP fetch) |     | (xlsx parse)|     | (normalize)   |     | (network)   |
+-------------+     +-------------+     +---------------+     +-------------+
                                                                     |
                    +-------------+     +-------------+              |
                    |  Dashboard  | <-- |  Analyzer   | <------------+
                    | (Streamlit) |     | (analysis)  |
                    +-------------+     +-------------+
```

## Installation

### Requirements

- Python 3.10+
- pip or conda

### Setup

```bash
# Clone repository
git clone https://github.com/your-username/3gpp-network-analysis.git
cd 3gpp-network-analysis

# Create virtual environment (optional)
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

## Usage

### Run Full Pipeline

```bash
# Collect -> Parse -> Preprocess -> Build Network -> Analyze
python -m src.scheduler run-all
```

### Run Individual Stages

```bash
# 1. Data Collection (download from 3GPP FTP)
python -m src.collector

# 2. Parsing
python -m src.parser

# 3. Preprocessing
python -m src.preprocessor

# 4. Network Building
python -m src.network

# 5. Analysis
python -m src.analyzer
```

### Run Dashboard

```bash
streamlit run src/dashboard/app.py
```

## Directory Structure

```
3gpp-network-analysis/
├── config/                     # Configuration files
│   ├── analysis.yaml          # Analysis settings
│   ├── collector.yaml         # Collector settings
│   ├── network.yaml           # Network building settings
│   ├── pipeline.yaml          # Pipeline settings
│   └── preprocessing.yaml     # Preprocessing settings
├── data/                       # Data directory (gitignored)
│   ├── raw/{RAN,SA,CT}/       # xlsx files collected from FTP
│   ├── interim/               # Parsed/preprocessed parquet files
│   ├── processed/             # Network edge list files
│   │   ├── company/           # Company collaboration network
│   │   └── wi/                # Work Item association network
│   └── results/               # Analysis results
├── src/                        # Source code
│   ├── analyzer/              # Network analysis module
│   ├── collector/             # FTP data collector
│   ├── dashboard/             # Streamlit dashboard
│   ├── network/               # Network building module
│   ├── parser/                # TDoc parsing module
│   ├── preprocessor/          # Data preprocessing module
│   ├── scheduler/             # Pipeline scheduler
│   └── utils/                 # Utility modules
├── tests/                      # Test code
├── .kiro/specs/               # Kiro spec documents
├── pyproject.toml             # Project configuration
├── requirements.txt           # Python dependencies
└── README.md
```

## Configuration

### config/pipeline.yaml

```yaml
data_dirs:
  raw: "data/raw"
  interim: "data/interim"
  processed: "data/processed"
  results: "data/results"

date_range:
  min_year: 2020

stages:
  collect: true
  parse: true
  preprocess: true
  build: true
  analyze: true
```

### config/network.yaml

```yaml
company:
  edge_threshold: 3
  similarity_method: "jaccard"

wi:
  edge_threshold: 2
  similarity_method: "jaccard"
```

## Testing

```bash
# Run all tests
pytest tests/ -v

# With coverage
pytest tests/ --cov=src --cov-report=html
```

## Analysis Output

### Company Collaboration Network
- **Nodes**: 3GPP contributing companies (Samsung, Qualcomm, Huawei, etc.)
- **Edges**: Connections between companies that co-contributed to the same TDoc
- **Analysis**: Centrality analysis to identify key players, community detection to discover collaboration groups

### Work Item Association Network
- **Nodes**: 3GPP Work Items (technical work items)
- **Edges**: Connections between WIs contributed by the same company
- **Analysis**: Identify relationships between technical areas, discover core technical items

## License

MIT License

## References

- [3GPP Official Website](https://www.3gpp.org/)
- [3GPP FTP Server](https://www.3gpp.org/ftp/)
