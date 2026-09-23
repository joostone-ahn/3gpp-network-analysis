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

```bash
git clone https://github.com/joostone-ahn/3gpp-network-analysis.git
cd 3gpp-network-analysis
pip install -r requirements.txt
```

## Usage

```bash
# Run full pipeline
python -m src.scheduler run-all

# Run dashboard
PYTHONPATH=. streamlit run src/dashboard/app.py
```

## Testing

```bash
pytest tests/ -v
```

## License

MIT License
