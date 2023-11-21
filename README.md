
# Liquidity Analysis and CBRT OMO

## Overview

This repository contains a Python script for fetching, processing, and visualizing data from the Turkish Central Bank's Analytical Balance Sheet. The focus is on analyzing liquidity and the CBRT OMO (Open Market Operations) over a specified time range.
Article: https://www.researchgate.net/publication/342637770_NEW_MONETARY_ANALYSIS_TOOL_THE_DAILY_LIQUIDITY_DATASET"

## Installation

Ensure you have the required packages installed by running the following commands:

pip install evds --upgrade
pip install plotnine


## Usage

Obtain a CBRT API key from [CBRT Profile Page](https://evds2.tcmb.gov.tr-Profile Page-API Key).
Replace 'YOUR_CBRT_API_KEY' in the script with your actual CBRT API key.
Adjust the date range and other parameters as needed.
Run the script to fetch data, process it, and generate visualizations.

## Data Source
The script utilizes the evds library to fetch data from the Central Bank Analytical Balance Sheet. You can customize the data parameters and frequency as needed.

## Visualization
The script produces visualizations using the plotnine library, illustrating the liquidity situation and CBRT OMO over the specified time range.


Feel free to customize and extend the script for your specific needs!
