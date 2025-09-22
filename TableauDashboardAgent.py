from oci.addons.adk import AgentClient, Agent, tool
import os, logging, importlib, time, json, sys
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service 
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from webdriver_manager.chrome import ChromeDriverManager
import requests
from bs4 import BeautifulSoup

# Load environment config
ENV = os.getenv("ENV", "AGENT").upper()
try:
    l_env = importlib.import_module(f"config_{ENV}")
except ModuleNotFoundError:
    raise Exception(f"Configuration for environment '{ENV}' not found.")

# Setup logging
current_date = datetime.now().strftime("%d%m%Y")
log_file = f"{l_env.LOG_PATH}-{current_date}.log"

# Create log directory if it doesn't exist
log_dir = os.path.dirname(log_file)
if log_dir and not os.path.exists(log_dir):
    os.makedirs(log_dir, exist_ok=True)

logging.basicConfig(
    filename=log_file,
    filemode="a",
    format="%(asctime)s - %(levelname)s - %(message)s",
    level=logging.DEBUG,
)

# --- DEBUG HELPERS (temporary) ---------------------------------------------
# When diagnosing OCI SDK or HTTP issues enable debug logging so the outgoing
# request URL, headers and responses are printed to stdout. Keep this optional
# and temporary for troubleshooting.
def enable_oci_debug():
    # Ensure the root logger prints to stdout
    root = logging.getLogger()
    if not any(isinstance(h, logging.StreamHandler) for h in root.handlers):
        handler = logging.StreamHandler(sys.stdout)
        handler.setLevel(logging.DEBUG)
        handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))
        root.addHandler(handler)

    logging.getLogger('oci').setLevel(logging.DEBUG)
    logging.getLogger('urllib3').setLevel(logging.DEBUG)

# Call this during troubleshooting to get full request/response details
# enable_oci_debug()
# ---------------------------------------------------------------------------

class TableauDashboardAgent:
    def __init__(self):
        self.driver = None
        self.wait = None
        self.dashboard_url = l_env.TABLEAU_DASHBOARD_URL
        
    def setup_driver(self):
        """Initialize Chrome WebDriver with appropriate options"""
        from webdriver_manager.chrome import ChromeDriverManager
        chrome_options = Options()
        chrome_options.add_argument("--headless")  # Run in background
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--window-size=1920,1080")
        
        #self.driver = webdriver.Chrome(options=chrome_options)
        #self.driver = webdriver.Chrome(options=chrome_options, service=Service('/Applications/Brave Browser.app/Contents/MacOS/Brave Browser'))
        self.driver = webdriver.Chrome(options=chrome_options, service=Service(ChromeDriverManager().install()))
        self.wait = WebDriverWait(self.driver, 20)
        logging.info("Chrome WebDriver initialized successfully")
        
    def navigate_to_dashboard(self):
        """Navigate directly to the Tableau dashboard"""
        try:
            self.driver.get(self.dashboard_url)
            time.sleep(5)  # Wait for dashboard to fully load
            
            # Wait for dashboard content to be present
            self.wait.until(EC.presence_of_element_located((By.TAG_NAME, "body")))
            logging.info("Successfully navigated to Tableau dashboard")
                
        except Exception as e:
            logging.error(f"Failed to navigate to dashboard: {e}")
            raise e
            
    def apply_filter(self, filter_name, filter_value, available_filters=None):
        """Apply a specific filter to the Tableau dashboard"""
        try:
            # If we have available filters, use them to find the right element
            if available_filters:
                target_filter = None
                for filter_item in available_filters:
                    # Fix: Clean the filter name for comparison
                    filter_clean = filter_item["name"].replace('\n', ' ').replace('Filter', '').replace('Inclusive', '').replace('(All)', '').strip()
                    if filter_name.lower() in filter_clean.lower() or filter_clean.lower() in filter_name.lower():
                        target_filter = filter_item
                        logging.info(f"Found matching filter: {filter_item['name']} -> {filter_clean}")
                        break
                
                if target_filter:
                    return self._apply_tableau_filter(target_filter, filter_value)
                else:
                    logging.warning(f"No matching filter found for: {filter_name}")
            
            # Fallback: try to find filter by name
            filter_selectors = [
                f"//div[contains(@class, 'tabComboBox') and contains(text(), '{filter_name}')]",
                f"//div[contains(@class, 'filter') and contains(text(), '{filter_name}')]",
                f"//select[contains(@title, '{filter_name}')]",
                f"//div[@role='button' and contains(text(), '{filter_name}')]"
            ]
            
            for selector in filter_selectors:
                try:
                    filter_element = self.driver.find_element(By.XPATH, selector)
                    return self._apply_tableau_filter({
                        "element": filter_element,
                        "name": filter_name,
                        "type": filter_element.tag_name
                    }, filter_value)
                except:
                    continue
            
            logging.warning(f"Could not find filter: {filter_name}")
            return False
            
        except Exception as e:
            logging.error(f"Failed to apply filter {filter_name}: {e}")
            return False
    
    def _apply_tableau_filter(self, filter_item, filter_value):
        """Apply a Tableau filter using the filter item"""
        try:
            element = filter_item["element"]
            filter_name = filter_item["name"]
            
            # For select elements
            if element.tag_name == "select":
                select = Select(element)
                try:
                    select.select_by_visible_text(filter_value)
                    logging.info(f"Applied select filter: {filter_name} = {filter_value}")
                    return True
                except:
                    # Try partial match
                    for option in select.options:
                        if filter_value.lower() in option.text.lower():
                            select.select_by_visible_text(option.text)
                            logging.info(f"Applied select filter (partial match): {filter_name} = {option.text}")
                            return True
            
            # For Tableau dropdown elements
            elif "tabComboBox" in element.get_attribute("class"):
                try:
                    # Click to open dropdown
                    element.click()
                    time.sleep(1)
                    
                    # Look for the option
                    option_selectors = [
                        f"//div[contains(@class, 'tabComboBoxItem') and contains(text(), '{filter_value}')]",
                        f"//li[contains(text(), '{filter_value}')]",
                        f"//div[@role='option' and contains(text(), '{filter_value}')]"
                    ]
                    
                    for option_selector in option_selectors:
                        try:
                            option_element = self.driver.find_element(By.XPATH, option_selector)
                            option_element.click()
                            time.sleep(1)
                            logging.info(f"Applied Tableau dropdown filter: {filter_name} = {filter_value}")
                            return True
                        except:
                            continue
                    
                    # If exact match fails, try partial match
                    option_elements = self.driver.find_elements(By.XPATH, "//div[contains(@class, 'tabComboBoxItem')] | //li | //div[@role='option']")
                    for option_element in option_elements:
                        if filter_value.lower() in option_element.text.lower():
                            option_element.click()
                            time.sleep(1)
                            logging.info(f"Applied Tableau dropdown filter (partial match): {filter_name} = {option_element.text}")
                            return True
                    
                    # Close dropdown if no option found
                    self.driver.find_element(By.TAG_NAME, "body").click()
                    
                except Exception as e:
                    logging.debug(f"Could not apply Tableau dropdown filter: {e}")
            
            # For button-based filters
            elif element.tag_name == "button" or "button" in element.get_attribute("class"):
                try:
                    element.click()
                    time.sleep(1)
                    logging.info(f"Applied button filter: {filter_name}")
                    return True
                except Exception as e:
                    logging.debug(f"Could not apply button filter: {e}")
            
            return False
            
        except Exception as e:
            logging.error(f"Failed to apply Tableau filter: {e}")
            return False
    
    def click_apply_button(self):
        """Click the Apply button to reload the dashboard with filtered data"""
        try:
            # Look for Apply button with various selectors
            apply_selectors = [
                "//button[contains(text(), 'Apply')]",
                "//button[contains(@class, 'apply')]",
                "//input[@type='button' and contains(@value, 'Apply')]",
                "//div[contains(@class, 'apply')]//button",
                "//button[contains(@title, 'Apply')]"
            ]
            
            for selector in apply_selectors:
                try:
                    apply_button = self.driver.find_element(By.XPATH, selector)
                    apply_button.click()
                    logging.info("Clicked Apply button to reload dashboard")
                    time.sleep(5)  # Wait for dashboard to reload
                    return True
                except:
                    continue
            
            logging.warning("Could not find Apply button")
            return False
            
        except Exception as e:
            logging.error(f"Failed to click Apply button: {e}")
            return False
            
    def extract_chart_data(self):
        """Extract data from visible Tableau charts on the dashboard"""
        chart_data = []
        try:
            # Wait for charts to load
            time.sleep(3)
            
            # Tableau-specific chart selectors
            tableau_chart_selectors = [
                "//div[contains(@class, 'tab-viz')]",
                "//div[contains(@class, 'tabCanvas')]",
                "//div[contains(@class, 'tabSheet')]",
                "//div[contains(@class, 'tabWorksheet')]",
                "//div[contains(@class, 'tabDashboard')]",
                "//svg[contains(@class, 'tab')]",
                "//canvas[contains(@class, 'tab')]",
                # Generic chart elements
                "//div[contains(@class, 'chart')]",
                "//svg",
                "//canvas"
            ]
            
            for selector in tableau_chart_selectors:
                try:
                    charts = self.driver.find_elements(By.XPATH, selector)
                    for chart in charts:
                        chart_info = self._extract_tableau_chart_info(chart)
                        if chart_info and chart_info.get("data"):
                            chart_data.append(chart_info)
                except Exception as e:
                    logging.debug(f"Selector {selector} failed: {e}")
                    continue
            
            # Also try to extract data from text elements that might contain chart data
            text_data = self._extract_text_data()
            if text_data:
                chart_data.append({
                    "type": "text_data",
                    "data": text_data,
                    "title": "Dashboard Text Data"
                })
            
            logging.info(f"Extracted data from {len(chart_data)} Tableau charts")
            return chart_data
            
        except Exception as e:
            logging.error(f"Failed to extract Tableau chart data: {e}")
            return []
    
    def _extract_tableau_chart_info(self, chart_element):
        """Extract information from a single Tableau chart element"""
        try:
            chart_info = {
                "type": "unknown",
                "data": [],
                "title": "",
                "element_type": chart_element.tag_name
            }
            
            # Try to get chart title
            title_selectors = [
                ".//div[contains(@class, 'title')]",
                ".//div[contains(@class, 'tabTitle')]",
                ".//h1", ".//h2", ".//h3",
                ".//div[contains(@class, 'caption')]",
                ".//div[contains(@class, 'tabCaption')]"
            ]
            
            for title_selector in title_selectors:
                try:
                    title_element = chart_element.find_element(By.XPATH, title_selector)
                    if title_element.text.strip():
                        chart_info["title"] = title_element.text.strip()
                        break
                except:
                    continue
            
            # Extract text content from chart
            chart_text = chart_element.text.strip()
            if chart_text:
                # Split by lines and clean up
                lines = [line.strip() for line in chart_text.split('\n') if line.strip()]
                chart_info["data"] = lines
            
            # For SVG elements, try to extract data from text elements
            if chart_element.tag_name == "svg":
                svg_text_elements = chart_element.find_elements(By.XPATH, ".//text")
                svg_data = [elem.text.strip() for elem in svg_text_elements if elem.text.strip()]
                if svg_data:
                    chart_info["data"].extend(svg_data)
                    chart_info["type"] = "svg_chart"
            
            # For canvas elements, try to extract any accessible text
            elif chart_element.tag_name == "canvas":
                chart_info["type"] = "canvas_chart"
                # Canvas elements are harder to extract data from
                # We'll rely on surrounding text elements
            
            # Determine chart type based on content
            if "bar" in chart_text.lower() or "column" in chart_text.lower():
                chart_info["type"] = "bar_chart"
            elif "pie" in chart_text.lower():
                chart_info["type"] = "pie_chart"
            elif "line" in chart_text.lower():
                chart_info["type"] = "line_chart"
            elif "table" in chart_text.lower():
                chart_info["type"] = "table"
            
            return chart_info
            
        except Exception as e:
            logging.debug(f"Could not extract chart info: {e}")
            return None
    
    def _extract_text_data(self):
        """Extract text data that might contain chart information"""
        try:
            # Look for text elements that might contain data
            text_selectors = [
                "//div[contains(@class, 'tabText')]",
                "//div[contains(@class, 'tabLabel')]",
                "//div[contains(@class, 'tabValue')]",
                "//span[contains(@class, 'tab')]",
                "//div[contains(text(), 'Total')]",
                "//div[contains(text(), 'Count')]",
                "//div[contains(text(), 'Sum')]"
            ]
            
            text_data = []
            for selector in text_selectors:
                try:
                    elements = self.driver.find_elements(By.XPATH, selector)
                    for element in elements:
                        text = element.text.strip()
                        if text and len(text) > 0:
                            text_data.append(text)
                except:
                    continue
            
            return text_data
            
        except Exception as e:
            logging.debug(f"Could not extract text data: {e}")
            return []
            
    def discover_available_filters(self):
        """Dynamically discover all available filters on the Tableau dashboard"""
        available_filters = []
        
        try:
            # Wait for dashboard to fully load
            time.sleep(5)
            
            # Tableau-specific filter selectors
            tableau_filter_selectors = [
                # Standard Tableau filter dropdowns
                "//div[contains(@class, 'tabComboBox')]",
                "//div[contains(@class, 'tabComboBoxContainer')]",
                "//div[contains(@class, 'filter')]",
                "//div[contains(@class, 'tabComboBoxButton')]",
                "//div[contains(@class, 'tabComboBoxText')]",
                # Tableau parameter controls
                "//div[contains(@class, 'tabParameterControl')]",
                "//div[contains(@class, 'tabParameterControlContainer')]",
                # Generic dropdowns that might be filters
                "//select[contains(@class, 'filter')]",
                "//select[contains(@title, 'filter')]",
                "//div[contains(@class, 'dropdown')]",
                # Tableau quick filters
                "//div[contains(@class, 'tabQuickFilter')]",
                "//div[contains(@class, 'tabQuickFilterContainer')]",
                # Look for any clickable elements that might be filters
                "//div[@role='button' and contains(@class, 'tab')]",
                "//div[@role='combobox']",
                "//div[@role='listbox']"
            ]
            
            for selector in tableau_filter_selectors:
                try:
                    elements = self.driver.find_elements(By.XPATH, selector)
                    for element in elements:
                        try:
                            # Get filter name/label
                            filter_name = self._extract_filter_name(element)
                            
                            if filter_name and filter_name != "Unknown Filter":
                                # Get available options
                                options = self._extract_filter_options(element)
                                
                                available_filters.append({
                                    "name": filter_name,
                                    "element": element,
                                    "options": options,
                                    "type": element.tag_name,
                                    "selector": selector
                                })
                                
                        except Exception as e:
                            logging.debug(f"Could not process filter element: {e}")
                            continue
                            
                except Exception as e:
                    logging.debug(f"Selector {selector} failed: {e}")
                    continue
            
            # Remove duplicates based on filter name
            unique_filters = []
            seen_names = set()
            for filter_item in available_filters:
                if filter_item["name"] not in seen_names:
                    unique_filters.append(filter_item)
                    seen_names.add(filter_item["name"])
            
            logging.info(f"Discovered {len(unique_filters)} unique Tableau filters")
            return unique_filters
            
        except Exception as e:
            logging.error(f"Failed to discover Tableau filters: {e}")
            return []
    
    def _extract_filter_name(self, element):
        """Extract filter name from Tableau element"""
        try:
            # Try multiple methods to get filter name
            name_attributes = [
                element.get_attribute("title"),
                element.get_attribute("aria-label"),
                element.get_attribute("name"),
                element.get_attribute("data-testid"),
                element.get_attribute("data-tb-test-id")
            ]
            
            # Get text content
            text_content = element.text.strip()
            
            # Look for label in parent elements
            parent_text = ""
            try:
                parent = element.find_element(By.XPATH, "./..")
                parent_text = parent.text.strip()
            except:
                pass
            
            # Combine all possible names
            all_names = [name for name in name_attributes if name] + [text_content, parent_text]
            
            # Return the first meaningful name
            for name in all_names:
                if name and len(name.strip()) > 0 and name.strip() != "(All)":
                    return name.strip()
            
            return "Unknown Filter"
            
        except Exception as e:
            logging.debug(f"Could not extract filter name: {e}")
            return "Unknown Filter"
    
    def _extract_filter_options(self, element):
        """Extract available options from Tableau filter element"""
        try:
            options = []
            
            # For select elements
            if element.tag_name == "select":
                select = Select(element)
                options = [option.text.strip() for option in select.options if option.text.strip()]
            
            # For Tableau dropdowns, try to click and get options
            elif "tabComboBox" in element.get_attribute("class") or "dropdown" in element.get_attribute("class"):
                try:
                    # Click to open dropdown
                    element.click()
                    time.sleep(1)
                    
                    # Look for option elements
                    option_elements = self.driver.find_elements(By.XPATH, "//div[contains(@class, 'tabComboBoxItem')] | //li[contains(@class, 'option')] | //div[@role='option']")
                    options = [opt.text.strip() for opt in option_elements if opt.text.strip()]
                    
                    # Click elsewhere to close dropdown
                    self.driver.find_element(By.TAG_NAME, "body").click()
                    
                except Exception as e:
                    logging.debug(f"Could not extract dropdown options: {e}")
                    options = ["Click to see options"]
            
            return options
            
        except Exception as e:
            logging.debug(f"Could not extract filter options: {e}")
            return []

    def get_dashboard_summary(self):
        """Get a summary of the current dashboard state"""
        try:
            summary = {
                "url": self.driver.current_url,
                "title": self.driver.title,
                "charts_count": len(self.driver.find_elements(By.XPATH, "//div[contains(@class, 'chart')] | //svg | //canvas")),
                "filters_applied": [],
                "available_filters": self.discover_available_filters(),
                "chart_data": self.extract_chart_data()
            }
            
            # Get applied filters
            filter_elements = self.driver.find_elements(By.XPATH, "//select[contains(@class, 'filter')]")
            for filter_elem in filter_elements:
                try:
                    select = Select(filter_elem)
                    selected_option = select.first_selected_option
                    summary["filters_applied"].append({
                        "name": filter_elem.get_attribute("title"),
                        "value": selected_option.text
                    })
                except:
                    pass
                    
            return summary
            
        except Exception as e:
            logging.error(f"Failed to get dashboard summary: {e}")
            return {"error": str(e)}
            
    def close_driver(self):
        """Close the WebDriver"""
        if self.driver:
            self.driver.quit()
            logging.info("WebDriver closed successfully")

# Global agent instance
tableau_agent = TableauDashboardAgent()

@tool(description="Analyzes Tableau dashboard data by applying filters and extracting insights from charts")
def analyze_tableau_dashboard(question: str):
    """
    Analyzes a Tableau dashboard based on user questions.
    Applies appropriate filters and extracts data from charts.
    """
    try:
        # Initialize the agent
        tableau_agent.setup_driver()
        tableau_agent.navigate_to_dashboard()
        
        # Get dashboard summary first to discover available filters
        summary = tableau_agent.get_dashboard_summary()
        
        # Parse question to determine filters to apply using available filters
        available_filter_names = [f["name"] for f in summary.get("available_filters", [])]
        filters_to_apply = parse_question_for_filters(question, available_filter_names)
        
        # Log the filters that will be applied
        logging.info(f"Question: {question}")
        logging.info(f"Available filters: {available_filter_names}")
        logging.info(f"Filters to apply: {filters_to_apply}")
        
        # Debug: Log extracted entities
        entities = extract_entities_from_question(question.lower())
        logging.info(f"Extracted entities: {entities}")
        
        # Apply filters using discovered available filters
        filters_applied_successfully = []
        
        for filter_name, filter_value in filters_to_apply:
            success = tableau_agent.apply_filter(filter_name, filter_value, summary.get("available_filters", []))
            if success:
                filters_applied_successfully.append((filter_name, filter_value))
                # Wait for dashboard to update after each filter
                time.sleep(2)
        
        # Click Apply button to reload dashboard with filtered data
        if filters_applied_successfully:
            tableau_agent.click_apply_button()
            
        # Get updated dashboard summary after applying filters and clicking Apply
        summary = tableau_agent.get_dashboard_summary()
        
        # Extract specific data based on the question
        specific_data = extract_specific_data_for_question(question, summary)
        summary["specific_data"] = specific_data
        
        # Generate response based on question and data
        response = generate_response(question, summary)
        
        return {
            "question": question,
            "response": response,
            "dashboard_summary": summary,
            "filters_applied": filters_to_apply
        }
        
    except Exception as e:
        logging.error(f"Failed to analyze dashboard: {e}")
        return {"error": str(e)}
        
    finally:
        tableau_agent.close_driver()

def parse_question_for_filters(question: str, available_filters: list):
    """Intelligently parse user question to determine which filters to apply"""
    filters = []
    question_lower = question.lower()
    
    # Extract entities from question using NLP-like approach
    entities = extract_entities_from_question(question_lower)
    
    # Match entities to available filters
    for entity_type, entity_value in entities.items():
        best_match = find_best_filter_match(entity_type, entity_value, available_filters)
        if best_match:
            filters.append(best_match)
    
    return filters

def extract_entities_from_question(question_lower: str):
    """Extract entities and their types from ANY question dynamically"""
    entities = {}
    import re
    
    # Extract location entities (colleges, universities, cities, etc.)
    # Fix: Use the original question case, not just lowercase
    question_original = question_lower  # Keep original for better matching
    
    # Simple pattern matching for common college names
    college_names = ['lehman', 'baruch', 'queens', 'brooklyn', 'hunter', 'city college', 'bronx', 'staten island']
    for college in college_names:
        if college in question_lower:
            # Handle special cases
            if college == 'lehman':
                entities['location'] = 'Lehman'
            elif college == 'city college':
                entities['location'] = 'City College'
            else:
                entities['location'] = college.title()
            break
    
    # If no specific college found, try regex patterns
    if 'location' not in entities:
        location_patterns = [
            r'\b([a-z]+(?:\s+[a-z]+)*)\s+(?:college|university|school|institution)\b',
            r'\b([a-z]+(?:\s+[a-z]+)*)\s+(?:city|state|county)\b'
        ]
        
        for pattern in location_patterns:
            matches = re.findall(pattern, question_lower)
            if matches:
                entities['location'] = matches[0].title()
                break
    
    # Extract degree level entities
    degree_patterns = {
        'bachelor': ['bachelor', 'bachelors', 'bachelor\'s'],
        'master': ['master', 'masters', 'master\'s'],
        'associate': ['associate'],
        'certificate': ['certificate'],
        'doctoral': ['doctoral', 'phd', 'doctorate']
    }
    
    for degree_type, keywords in degree_patterns.items():
        for keyword in keywords:
            if keyword in question_lower:
                entities['degree'] = degree_type.title() + ("'s" if degree_type in ['bachelor', 'master'] else "")
                break
        if 'degree' in entities:
            break
    
    # Extract category entities (STEM, Business, etc.)
    category_patterns = {
        'stem': ['stem'],
        'business': ['business', 'commerce'],
        'engineering': ['engineering'],
        'arts': ['arts', 'art'],
        'science': ['science', 'scientific'],
        'education': ['education', 'teaching'],
        'medicine': ['medicine', 'medical'],
        'law': ['law', 'legal'],
        'technology': ['technology', 'tech']
    }
    
    for category, keywords in category_patterns.items():
        for keyword in keywords:
            if keyword in question_lower:
                entities['category'] = category.title()
                break
        if 'category' in entities:
            break
    
    # Extract program/subject entities (any capitalized words that might be programs)
    import re
    # Look for capitalized words that might be program names
    program_words = re.findall(r'\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b', question_lower.title())
    
    # Filter out common words and keep potential program names
    common_words = {'The', 'And', 'Or', 'But', 'In', 'On', 'At', 'To', 'For', 'Of', 'With', 'By', 'From', 'How', 'What', 'When', 'Where', 'Why', 'Which', 'Who'}
    potential_programs = [word for word in program_words if word not in common_words and len(word) > 3]
    
    if potential_programs:
        entities['program'] = potential_programs[0]
    
    # Extract time entities
    time_patterns = [r'\b(20\d{2})\b', r'\b(current|recent|latest)\b', r'\b(last\s+year|this\s+year)\b']
    for pattern in time_patterns:
        matches = re.findall(pattern, question_lower)
        if matches:
            entities['time'] = matches[0]
            break
    
    return entities

def extract_value_around_keyword(question_lower: str, keyword: str):
    """Extract the actual value mentioned around a keyword"""
    words = question_lower.split()
    keyword_index = -1
    
    # Find keyword position
    for i, word in enumerate(words):
        if keyword in word:
            keyword_index = i
            break
    
    if keyword_index == -1:
        return None
    
    # Extract surrounding words (context)
    start = max(0, keyword_index - 2)
    end = min(len(words), keyword_index + 3)
    context_words = words[start:end]
    
    # Return the most relevant word (usually the keyword itself or adjacent)
    return keyword

def find_best_filter_match(entity_type: str, entity_value: str, available_filters: list):
    """Find the best matching filter for an entity with intelligent matching"""
    
    # Enhanced filter mapping with more specific patterns
    filter_mapping = {
        'location': ['reporting college', 'enrolled college', 'college', 'university', 'institution', 'campus'],
        'degree': ['award level', 'award name', 'degree', 'level', 'program'],
        'category': ['stem category', 'category', 'type', 'classification'],
        'program': ['program name', 'academic plan', 'program', 'name', 'title'],
        'time': ['year', 'date', 'period'],
        'status': ['status', 'state', 'condition']
    }
    
    # Find filters that might match this entity type
    possible_filters = filter_mapping.get(entity_type, [])
    
    best_match_score = 0
    best_match = None
    
    for filter_name in available_filters:
        # Fix: Handle complex filter names like "Filter\nReporting College\nInclusive\n(All)"
        filter_clean = filter_name.replace('\n', ' ').replace('Filter', '').replace('Inclusive', '').replace('(All)', '').strip()
        filter_lower = filter_clean.lower()
        
        # Calculate match score
        score = 0
        for possible_filter in possible_filters:
            if possible_filter in filter_lower:
                # Exact match gets higher score
                if possible_filter == filter_lower:
                    score += 10
                # Partial match gets lower score
                else:
                    score += 5
        
        # Special handling for specific entity types
        if entity_type == 'location':
            if 'reporting college' in filter_lower:
                score += 15  # Highest priority for location
            elif 'enrolled college' in filter_lower:
                score += 10
        elif entity_type == 'degree':
            if 'award level' in filter_lower:
                score += 15  # Highest priority for degree
            elif 'award name' in filter_lower:
                score += 10
        
        if score > best_match_score:
            best_match_score = score
            best_match = (filter_name, entity_value)  # Return original filter name
    
    return best_match

def extract_specific_data_for_question(question: str, summary: dict):
    """Extract specific data relevant to ANY user's question dynamically"""
    specific_data = {}
    question_lower = question.lower()
    
    # Extract all text data from charts
    all_text_data = []
    for chart in summary.get("chart_data", []):
        if chart.get("data"):
            all_text_data.extend(chart["data"])
    
    # Extract entities from the question to find relevant data
    entities = extract_entities_from_question(question_lower)
    
    # Look for count/number questions
    if "how many" in question_lower or "count" in question_lower or "number" in question_lower:
        # Look for large, prominent numbers (likely the main answer)
        large_numbers = []
        small_numbers = []
        
        for text in all_text_data:
            import re
            numbers = re.findall(r'\d+', text)
            for num in numbers:
                num_int = int(num)
                if num_int >= 10:  # Focus on larger numbers (likely main counts)
                    large_numbers.append(num)
                else:
                    small_numbers.append(num)
        
        # Prioritize large numbers as they're likely the main answer
        if large_numbers:
            specific_data["counts"] = large_numbers
            specific_data["total_count"] = sum(int(n) for n in large_numbers)
            specific_data["main_answer"] = max(large_numbers, key=int)  # The largest number is likely the answer
        elif small_numbers:
            specific_data["counts"] = small_numbers
            specific_data["total_count"] = sum(int(n) for n in small_numbers)
    
    # Look for data related to extracted entities
    for entity_type, entity_value in entities.items():
        if entity_value:
            # Find data containing this entity
            entity_data = [text for text in all_text_data if entity_value.lower() in text.lower()]
            if entity_data:
                specific_data[f"{entity_type}_data"] = entity_data[:5]  # Limit to first 5 matches
    
    # Look for any capitalized words in the question that might be entities
    import re
    capitalized_words = re.findall(r'\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b', question)
    common_words = {'The', 'And', 'Or', 'But', 'In', 'On', 'At', 'To', 'For', 'Of', 'With', 'By', 'From', 'How', 'What', 'When', 'Where', 'Why', 'Which', 'Who'}
    
    for word in capitalized_words:
        if word not in common_words and len(word) > 3:
            # Look for data containing this word
            word_data = [text for text in all_text_data if word.lower() in text.lower()]
            if word_data:
                specific_data[f"{word.lower()}_data"] = word_data[:3]
    
    # Look for program/subject keywords
    program_keywords = ["program", "degree", "major", "course", "subject", "field", "department"]
    program_data = []
    for text in all_text_data:
        for keyword in program_keywords:
            if keyword in text.lower():
                program_data.append(text)
                break
    
    if program_data:
        specific_data["program_data"] = program_data[:10]  # Limit to first 10 programs
    
    # Look for comparison words
    if "compare" in question_lower or "vs" in question_lower or "versus" in question_lower:
        comparison_data = [text for text in all_text_data if any(word in text.lower() for word in ["vs", "versus", "compared", "comparison"])]
        if comparison_data:
            specific_data["comparison_data"] = comparison_data
    
    # Look for trend words
    if "trend" in question_lower or "change" in question_lower or "increase" in question_lower or "decrease" in question_lower:
        trend_data = [text for text in all_text_data if any(word in text.lower() for word in ["trend", "change", "increase", "decrease", "growth", "decline"])]
        if trend_data:
            specific_data["trend_data"] = trend_data
    
    return specific_data

def generate_response(question: str, summary: dict):
    """Generate a natural language response based on the question and dashboard data"""
    response_parts = []
    
    # Add context about filters applied
    if summary.get("filters_applied"):
        filter_info = ", ".join([f"{f['name']}: {f['value']}" for f in summary["filters_applied"]])
        response_parts.append(f"📊 Applied filters: {filter_info}")
    else:
        response_parts.append("📊 No specific filters were applied")
    
    # Add available filters info
    if summary.get("available_filters"):
        filter_names = [f["name"] for f in summary["available_filters"]]
        response_parts.append(f"🔍 Available filters: {', '.join(filter_names[:5])}{'...' if len(filter_names) > 5 else ''}")
    
    # Add chart data insights
    if summary.get("chart_data"):
        response_parts.append(f"📈 Found {summary['charts_count']} charts with data")
        
        # Extract meaningful data from charts
        meaningful_data = []
        for chart in summary["chart_data"]:
            if chart.get("data") and len(chart["data"]) > 0:
                chart_title = chart.get("title", "Untitled Chart")
                data_preview = chart["data"][:3]  # Show first 3 data points
                meaningful_data.append(f"• {chart_title}: {', '.join(data_preview)}")
        
        if meaningful_data:
            response_parts.extend(meaningful_data[:3])  # Show top 3 charts
        else:
            response_parts.append("📊 Charts detected but no readable data extracted")
    
    # Add specific insights based on question and extracted data
    question_lower = question.lower()
    specific_data = summary.get("specific_data", {})
    
    # Handle count/number questions
    if "count" in question_lower or "how many" in question_lower or "number" in question_lower:
        if specific_data.get("main_answer"):
            # Use the main answer (largest number found)
            main_answer = specific_data["main_answer"]
            response_parts.append(f"🔢 **Answer: {main_answer}**")
        elif specific_data.get("total_count"):
            response_parts.append(f"🔢 **Answer: {specific_data['total_count']} items found**")
        elif specific_data.get("counts"):
            counts = specific_data["counts"]
            response_parts.append(f"🔢 **Numbers found in data: {', '.join(counts[:5])}**")
        else:
            response_parts.append("🔢 Looking for count data in the charts above")
    
    # Handle entity-specific data dynamically
    entities = extract_entities_from_question(question_lower)
    for entity_type, entity_value in entities.items():
        if entity_value and specific_data.get(f"{entity_type}_data"):
            data = specific_data[f"{entity_type}_data"]
            if entity_type == 'location':
                response_parts.append(f"🏫 **{entity_value} specific data:** {', '.join(data[:3])}")
            elif entity_type == 'degree':
                response_parts.append(f"🎓 **{entity_value} degree data:** {', '.join(data[:3])}")
            elif entity_type == 'category':
                response_parts.append(f"📊 **{entity_value} category data:** {', '.join(data[:3])}")
            elif entity_type == 'program':
                response_parts.append(f"📚 **{entity_value} program data:** {', '.join(data[:3])}")
    
    # Handle capitalized words from question
    import re
    capitalized_words = re.findall(r'\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b', question)
    common_words = {'The', 'And', 'Or', 'But', 'In', 'On', 'At', 'To', 'For', 'Of', 'With', 'By', 'From', 'How', 'What', 'When', 'Where', 'Why', 'Which', 'Who'}
    
    for word in capitalized_words:
        if word not in common_words and len(word) > 3 and specific_data.get(f"{word.lower()}_data"):
            data = specific_data[f"{word.lower()}_data"]
            response_parts.append(f"🔍 **{word} specific data:** {', '.join(data[:3])}")
    
    # Handle program data
    if specific_data.get("program_data"):
        response_parts.append(f"📚 **Program names found:** {', '.join(specific_data['program_data'][:5])}")
    
    # Handle comparison data
    if specific_data.get("comparison_data"):
        response_parts.append(f"📊 **Comparison data:** {', '.join(specific_data['comparison_data'][:3])}")
    
    # Handle trend data
    if specific_data.get("trend_data"):
        response_parts.append(f"📈 **Trend data:** {', '.join(specific_data['trend_data'][:3])}")
    
    # Fallback insights
    if not specific_data:
        if "compare" in question_lower:
            response_parts.append("📊 Comparison data available in the charts above")
        elif "trend" in question_lower:
            response_parts.append("📈 Trend analysis available in the dashboard charts")
        else:
            response_parts.append("📊 Data extracted from dashboard charts")
    
    # Add dashboard info
    if summary.get("title"):
        response_parts.append(f"📋 Dashboard: {summary['title']}")
    
    return "\n".join(response_parts) if response_parts else "Dashboard analysis completed successfully."

def main():
    client = AgentClient(
        auth_type="api_key",
        profile="DEFAULT",
        region="us-chicago-1"
    )

    agent = Agent(
        client=client,
        agent_endpoint_id="ocid1.genaiagentendpoint.oc1.us-chicago-1.amaaaaaakjeknfqa7qqxtgjcc2fauk2mi6u6oadru5o4bkjkxjy5gzbapq5q",
        #agent_endpoint_id="ocid1.genaiagent.oc1.us-chicago-1.amaaaaaaclx5faiaua5sya3pctds36jrmda675nzrfbtkx374pnsgs7w7qyq",
        instructions="You analyze Tableau dashboards by applying filters and extracting insights from charts. You can answer questions about data, apply specific filters, and provide summaries of dashboard content.",
        tools=[analyze_tableau_dashboard]
    )

    # Example questions
    sample_questions = [
        "Show me data for bachelor's degree programs",
        "Filter by college and show me the results",
        "What programs are available in STEM category?",
        "Compare data across different categories",
        "Show me trends in the data",
        "Filter by year and program type"
    ]
    
    print("Tableau Dashboard Agent Ready!")
    print("Sample questions you can ask:")
    for i, q in enumerate(sample_questions, 1):
        print(f"{i}. {q}")
    
    # Interactive mode
    while True:
        user_question = input("\nEnter your question (or 'quit' to exit): ")
        if user_question.lower() == 'quit':
            break
            
        response = agent.run(user_question)
        response.pretty_print()

if __name__ == "__main__":
    main()
