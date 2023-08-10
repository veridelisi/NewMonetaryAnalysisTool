pip install evds --upgrade

# Import pandas and numpy
import pandas as pd
import numpy as np
pip install plotnine 

# Import evds
from evds import evdsAPI

# Please put your  CBRT API key {https://evds2.tcmb.gov.tr-Profile Page-API Key}
evds = evdsAPI('k2QX6fe8eZ')

# We download datas in the range 2013-2023
# https://evds2.tcmb.gov.tr/index.php?/evds/DataGroupLink/2/bie_abanlbil/en
# Central Bank Analytical Balance Sheet (Thousand TRY)(Business)
# Foreign Assets | TP.AB.A02                  Domestic Assets | TP.AB.A03               FX Revaluation Account | TP.AB.A08
# Total Foreign Liabilities | TP.AB.A10       Currency Issued | TP.AB.A17  
# Extra Budgetary Funds | TP.AB.A21           Deposits of Non-Bank Sector | TP.AB.A22   Deposits of Public Sector | TP.AB.A25
# Deposits of Banking Sector  | TP.AB.A18     Open Market Operations | TP.AB.A24

df=evds.get_data(['TP.AB.A02','TP.AB.A03', 'TP.AB.A08','TP.AB.A10','TP.AB.A17','TP.AB.A18','TP.AB.A21','TP.AB.A24','TP.AB.A25','TP.AB.A22'], startdate="01-01-2013", enddate="09-08-2023")

# Rename columns
new_column_names = ['Date','Foreign Assets', 'Domestic Assets', 'Revaluation', 'Total Foreign Liabilities', 'Currency Issued', 'Banking Reserves', 'Extra Funds', 'OMO', 'Deposits of Public Sector', 'Deposits of Non-Bank Sector']
df.columns = new_column_names

# We choose Date column as the index column
df.set_index('Date', inplace=True)

# Drop the NAN rows
df=df.dropna()
df

# Calculate the difference between Foreign Assets and Total Foreign Liabilities. This is Net Foreign Assets.
df['Net Foreign Assets'] = df['Foreign Assets'] - df['Total Foreign Liabilities']
df

# Drop the Foreign Assets and Total Foreign Liabilities columns
df.drop(['Foreign Assets', 'Total Foreign Liabilities'], axis=1, inplace=True)
df

# Move the last column to the first position
last_column = df.pop('Net Foreign Assets')
df.insert(0, 'Net Foreign Assets', last_column)
df

# Calculate the first difference for all columns
df_diff = df.diff()

# Delete the first row 
df_diff  = df_diff .iloc[1:]
df_diff

# Calculate the liquidity Situation
df_diff['Liquidity'] = df_diff['Net Foreign Assets']+ df_diff['Domestic Assets']+ df_diff['Revaluation']- df_diff['Currency Issued']- df_diff['Extra Funds'] - df_diff['Deposits of Public Sector'] - df_diff['Deposits of Non-Bank Sector'] 
df_diff

# OMO account is normally asset account but CBRT puts it liabilities side. We need to multiply with -1
df_diff['OMO']=df_diff['OMO'] * (-1)
df_diff

# The sum of the Liquidity and OMO need to be equal a Banking Reserves
# We create new series for comparing with Banking Reserves
# Please control whether Banking Reserves is rougly equal to  Banking Reserves 2
df_diff['Banking Reserves 2']=df_diff['OMO'] + df_diff['Liquidity']
df_diff


# Import the necessary libraries
import pandas as pd
from plotnine import ggplot, aes, geom_col, theme_minimal, labs, scale_y_continuous, theme, element_text

# Sample data (replace this with your df_diff)
# ... (Your existing code to load and process the data)

# Convert the index to datetime with the correct format
df_diff.index = pd.to_datetime(df_diff.index, format="%d-%m-%Y")

# Calculate yearly sums for 'OMO' and 'Liquidity'
df_diff['Year'] = df_diff.index.year  # Add a 'Year' column
df_yearly = df_diff.groupby('Year')[['Liquidity', 'OMO']].sum()

# Reset index to make year a separate column
df_yearly.reset_index(inplace=True)

# Melt the DataFrame to long format for stacking
df_yearly_long = df_yearly.melt(id_vars=['Year'], value_vars=['Liquidity', 'OMO'], var_name='Category', value_name='Value')

# Create the stacked bar chart using Plotnine
p = (ggplot(df_yearly_long)
     + aes(x='Year', y='Value', fill='Category')
     + geom_col(position='stack', width=0.8)  # Adjust the width of the bars
     + scale_y_continuous(labels=lambda l: [f'{x/1e6:.0f}M' for x in l])  # Format y-axis labels in millions
     + theme_minimal()
     + labs(title="Yearly Stacked Bar Chart", x="Year", y="Value (Millions)")
     + theme(axis_text_x=element_text(angle=45, hjust=1, size=8))  # Rotate x-axis labels and adjust the size of tick labels
     + theme(figure_size=(12, 6))  # Adjust width and height of the graph
)

# Display the plot
print(p)



