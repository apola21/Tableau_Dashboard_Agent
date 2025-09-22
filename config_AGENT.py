import os

# Base directory for the project (this file's directory)
BASE_DIR = os.path.dirname(__file__)

# Log path base (the agent will append "-<DDMMYYYY>.log" to this value)
LOG_PATH = os.path.join(BASE_DIR, "logs", "tableau_agent")

# Tableau Dashboard Configuration
TABLEAU_DASHBOARD_URL = 'https://insights.cuny.edu/t/CUNYGuest/views/CUNYRegisteredProgramsInventory/ProgramCount?%3Aembed=y&%3AisGuestRedirectFromVizportal=y'