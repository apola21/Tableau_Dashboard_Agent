# Tableau Dashboard Agent Setup Guide

## 🚀 Quick Start

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Install Chrome WebDriver
```bash
# Install Chrome browser if not already installed
# Then install ChromeDriver
pip install webdriver-manager
```

### 3. Configure Settings
Update `config_AGENT.py` with your Tableau credentials:
```python
TABLEAU_DASHBOARD_URL = 'https://your-tableau-server.com/dashboard-url'
TABLEAU_USERNAME = 'your-username'
TABLEAU_PASSWORD = 'your-password'
```

### 4. Run the Agent
```bash
python TableauDashboardAgent.py
```

## 🎯 Features

### ✅ **Web Automation**
- Automatically logs into Tableau dashboards
- Applies filters based on user questions
- Extracts data from charts and visualizations

### ✅ **Smart Filter Selection**
- Maps natural language questions to appropriate filters
- Supports academic program inventory filters:
  - College selection (Lehman, Baruch, Queens, etc.)
  - Award levels (Bachelor's, Master's, Associate, etc.)
  - Program types (STEM, Accounting, Biology, etc.)

### ✅ **Chart Data Extraction**
- Reads multiple chart types (bar charts, pie charts, etc.)
- Extracts numerical data and labels
- Provides structured summaries

### ✅ **Natural Language Processing**
- Understands complex questions
- Generates human-readable responses
- Provides context about applied filters

## 📝 Example Questions

The agent can answer questions like:

1. **"How many bachelor's programs are available at Lehman College?"**
   - Applies: Reporting College = Lehman, Award Level = Bachelor's
   - Extracts: Program count from charts

2. **"Show me all STEM programs in the system"**
   - Applies: STEM Category = STEM
   - Extracts: All STEM program data

3. **"Compare accounting programs across different colleges"**
   - Applies: Program Name = Accounting
   - Extracts: Comparative data across colleges

4. **"What are the trends in master's degree programs?"**
   - Applies: Award Level = Master's
   - Extracts: Trend data from charts

## 🔧 Customization

### Adding New Filters
Edit the `parse_question_for_filters()` function to add new filter mappings:

```python
def parse_question_for_filters(question: str):
    filters = []
    question_lower = question.lower()
    
    # Add your custom filters here
    if "your_keyword" in question_lower:
        filters.append(("Filter Name", "Filter Value"))
    
    return filters
```

### Modifying Chart Extraction
Update the `extract_chart_data()` method to handle different chart types:

```python
def extract_chart_data(self):
    # Add custom chart extraction logic
    pass
```

## 🛠️ Troubleshooting

### Common Issues

1. **ChromeDriver not found**
   ```bash
   pip install webdriver-manager
   ```

2. **Login failures**
   - Check Tableau URL and credentials
   - Verify network connectivity
   - Check if 2FA is enabled

3. **Filter application fails**
   - Verify filter names match dashboard
   - Check if filters are available
   - Update filter selectors in code

### Debug Mode
Set `headless=False` in `setup_driver()` to see browser actions:
```python
chrome_options.add_argument("--headless")  # Remove this line
```

## 📊 Architecture

```
TableauDashboardAgent
├── WebDriver Setup (Chrome)
├── Authentication (Tableau Login)
├── Filter Application (Dynamic)
├── Chart Data Extraction
├── Natural Language Processing
└── Response Generation
```

## 🔒 Security Notes

- Store credentials securely in environment variables
- Use headless mode for production
- Implement proper error handling
- Log all actions for audit trails

## 📈 Performance Tips

- Use headless mode for faster execution
- Implement caching for repeated queries
- Optimize wait times for dashboard loading
- Use parallel processing for multiple charts

