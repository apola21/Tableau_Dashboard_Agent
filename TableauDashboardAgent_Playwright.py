from oci.addons.adk import AgentClient, Agent, tool
import os, logging, importlib, time, json, sys, subprocess
from datetime import datetime
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

# Also log to console for debugging
root = logging.getLogger()
if not root.handlers:
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(logging.DEBUG)
    handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))
    root.addHandler(handler)

class TableauDashboardAgent:
    def __init__(self):
        self.dashboard_url = l_env.TABLEAU_DASHBOARD_URL
        
    def run_playwright_script(self, question):
        """Run a Playwright script in a separate process to avoid event loop conflicts"""
        try:
            # Skip requests fallback for now - we need Playwright to apply filters
            logging.info("Using Playwright to apply filters and extract data...")
            
            # Create a clean temporary Python script
            script_content = f'''
import asyncio
import json
import time
import sys

# Test if Playwright is available
try:
    from playwright.async_api import async_playwright
    print("Playwright imported successfully")
except ImportError as e:
    print(f"Playwright import error: {{e}}")
    print(json.dumps({{"error": "Playwright not installed. Run: pip install playwright && playwright install"}}))
    sys.exit(1)

async def apply_filters_based_on_question(page, question):
    """Apply appropriate filters based on the user's question"""
    filters_applied = []
    
    try:
        print(f"Analyzing question: {{question}}")
        
        # Apply Award Level filter for degree-related questions
        if any(word in question for word in ['bachelor', 'master', 'associate', 'certificate', 'degree']):
            print("Applying Award Level filter...")
            result = await apply_award_level_filter(page, question)
            if result:
                filters_applied.append("Award Level")
        
        # Apply STEM Category filter for computer science questions
        if 'computer science' in question or 'stem' in question:
            print("Applying STEM Category filter...")
            result = await apply_stem_category_filter(page, 'Computer Science')
            if result:
                filters_applied.append("STEM Category")
        
        # Apply CIP Code filter for specific programs
        if 'computer science' in question:
            print("Applying CIP Code filter...")
            result = await apply_cip_filter(page, 'Computer Science')
            if result:
                filters_applied.append("CIP Code")
        
        print(f"Applied filters: {{filters_applied}}")
        
        # Click Apply button to reload dashboard
        print("Clicking Apply button...")
        apply_result = await click_apply_button(page)
        print(f"Apply button clicked: {{apply_result}}")
        
        # Wait for dashboard to fully reload with filtered data
        print("Waiting for dashboard reload...")
        await wait_for_dashboard_reload(page)
        print("Dashboard reload completed")
        
    except Exception as e:
        print(f"Error applying filters: {{e}}")

async def apply_award_level_filter(page, question):
    """Apply Award Level filter"""
    try:
        # Look for Award Level dropdown
        award_selectors = [
            'select[title*="Award Level"]',
            'select[aria-label*="Award Level"]',
            'div[class*="award"][class*="level"]',
            'div[class*="tabComboBox"]:has-text("Award Level")'
        ]
        
        for selector in award_selectors:
            try:
                element = await page.query_selector(selector)
                if element:
                    # For select elements
                    tag_name = await element.evaluate("el => el.tagName")
                    if tag_name.lower() == 'select':
                        if 'bachelor' in question:
                            await element.select_option(label="Bachelor's")
                        elif 'master' in question:
                            await element.select_option(label="Master's")
                        elif 'associate' in question:
                            await element.select_option(label="Associate")
                        print(f"Applied Award Level filter")
                        return True
                    
                    # For Tableau dropdown elements
                    else:
                        await element.click()
                        await asyncio.sleep(1)
                        
                        # Look for the option
                        if 'bachelor' in question:
                            option = await page.query_selector('div:has-text("Bachelor\\'s"), li:has-text("Bachelor\\'s")')
                        elif 'master' in question:
                            option = await page.query_selector('div:has-text("Master\\'s"), li:has-text("Master\\'s")')
                        elif 'associate' in question:
                            option = await page.query_selector('div:has-text("Associate"), li:has-text("Associate")')
                        
                        if option:
                            await option.click()
                            await asyncio.sleep(1)
                            print(f"Applied Award Level filter")
                            return True
            except:
                continue
    except Exception as e:
        print(f"Error applying Award Level filter: {{e}}")
    return False

async def apply_stem_category_filter(page, category):
    """Apply STEM Category filter"""
    try:
        # Look for STEM Category dropdown
        stem_selectors = [
            'select[title*="STEM Category"]',
            'select[aria-label*="STEM Category"]',
            'div[class*="stem"][class*="category"]',
            'div[class*="tabComboBox"]:has-text("STEM Category")'
        ]
        
        for selector in stem_selectors:
            try:
                element = await page.query_selector(selector)
                if element:
                    # For select elements
                    tag_name = await element.evaluate("el => el.tagName")
                    if tag_name.lower() == 'select':
                        await element.select_option(label=category)
                        print(f"Applied STEM Category filter: {{category}}")
                        return True
                    
                    # For Tableau dropdown elements
                    else:
                        await element.click()
                        await asyncio.sleep(1)
                        
                        # Look for the option
                        option = await page.query_selector(f'div:has-text("{{category}}"), li:has-text("{{category}}")')
                        if option:
                            await option.click()
                            await asyncio.sleep(1)
                            print(f"Applied STEM Category filter: {{category}}")
                            return True
            except:
                continue
    except Exception as e:
        print(f"Error applying STEM Category filter: {{e}}")
    return False

async def apply_cip_filter(page, program):
    """Apply CIP Code filter"""
    try:
        # Look for CIP Code dropdowns
        cip_selectors = [
            'select[title*="CIP"]',
            'select[aria-label*="CIP"]',
            'div[class*="cip"]',
            'div[class*="tabComboBox"]:has-text("CIP")'
        ]
        
        for selector in cip_selectors:
            try:
                element = await page.query_selector(selector)
                if element:
                    # For select elements
                    tag_name = await element.evaluate("el => el.tagName")
                    if tag_name.lower() == 'select':
                        # Look for Computer Science option
                        options = await element.query_selector_all('option')
                        for option in options:
                            text = await option.text_content()
                            if text and 'Computer Science' in text:
                                await element.select_option(label=text)
                                print(f"Applied CIP filter: {{text}}")
                                return True
                    
                    # For Tableau dropdown elements
                    else:
                        await element.click()
                        await asyncio.sleep(1)
                        
                        # Look for Computer Science option
                        option = await page.query_selector('div:has-text("Computer Science"), li:has-text("Computer Science")')
                        if option:
                            await option.click()
                            await asyncio.sleep(1)
                            print("Applied CIP filter: Computer Science")
                            return True
            except:
                continue
    except Exception as e:
        print(f"Error applying CIP filter: {{e}}")
    return False

async def click_apply_button(page):
    """Click the Apply button to reload the dashboard"""
    try:
        # Look for Apply button with various selectors
        apply_selectors = [
            'button:has-text("Apply")',
            'button[class*="apply"]',
            'input[type="button"][value*="Apply"]',
            'div[class*="apply"] button',
            'button[title*="Apply"]',
            'button:has-text("APPLY")',
            'input[value="Apply"]',
            'button[data-testid*="apply"]',
            'button[id*="apply"]',
            'div[role="button"]:has-text("Apply")',
            'a[role="button"]:has-text("Apply")'
        ]
        
        for selector in apply_selectors:
            try:
                apply_button = await page.query_selector(selector)
                if apply_button:
                    await apply_button.click()
                    print("Clicked Apply button")
                    return True
            except:
                continue
        
        print("Could not find Apply button")
        return False
        
    except Exception as e:
        print(f"Error clicking Apply button: {{e}}")
        return False

async def wait_for_dashboard_reload(page):
    """Wait for the dashboard to fully reload with filtered data"""
    try:
        print("Waiting for dashboard to reload...")
        
        # Wait for any loading indicators to disappear
        try:
            await page.wait_for_selector('.loading, .spinner, [class*="loading"]', state='hidden', timeout=10000)
        except:
            pass
        
        # Wait for Tableau-specific elements to be ready
        try:
            await page.wait_for_selector('[class*="tab-viz"], [class*="tabCanvas"], [class*="tabSheet"]', timeout=30000)
            print("Tableau elements loaded")
        except:
            print("Tableau elements not found, continuing...")
        
        # Wait for network to be idle
        try:
            await page.wait_for_load_state('networkidle', timeout=30000)
            print("Network is idle")
        except:
            print("Network idle timeout, continuing...")
        
        # Additional wait for dynamic content
        await asyncio.sleep(10)
        print("Additional wait completed")
        
        # Wait for specific data elements to appear
        try:
            await page.wait_for_function("""
                () => {{
                    const elements = document.querySelectorAll('div, span, td, th');
                    for (let el of elements) {{
                        const text = el.textContent || '';
                        if (text.match(/[A-Za-z\\s]+:\\s*\\d+/)) {{
                            return true;
                        }}
                    }}
                    return false;
                }}
            """, timeout=20000)
            print("Program count data found")
        except:
            print("Program count data not found, continuing...")
        
        print("Dashboard reload wait completed")
        
    except Exception as e:
        print(f"Error waiting for dashboard reload: {{e}}")
        await asyncio.sleep(15)

async def analyze_dashboard():
    try:
        playwright = await async_playwright().start()
        browser = await playwright.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-web-security",
                "--disable-features=VizDisplayCompositor",
                "--disable-extensions",
                "--disable-plugins",
                "--disable-images"
            ]
        )
        page = await browser.new_page(viewport={{"width": 1920, "height": 1080}})
        page.set_default_timeout(60000)
        
        # Navigate to dashboard
        await page.goto("{self.dashboard_url}", wait_until="domcontentloaded", timeout=60000)
        await page.wait_for_selector("body", timeout=30000)
        await asyncio.sleep(5)
        
        # Get page title
        title = await page.title()
        
        # Apply filters based on question
        print("Starting filter application...")
        await apply_filters_based_on_question(page, "{question}")
        print("Filter application completed")
        
        # Extract text content after applying filters
        text_content = await page.evaluate("""
            () => {{
                const elements = document.querySelectorAll('div, span, p, h1, h2, h3, h4, h5, h6');
                let text = '';
                elements.forEach(el => {{
                    if (el.textContent && el.textContent.trim()) {{
                        text += el.textContent.trim() + '\\n';
                    }}
                }});
                return text;
            }}
        """)
        
        # Look for filter elements
        filter_elements = await page.evaluate("""
            () => {{
                const filters = [];
                const elements = document.querySelectorAll('div[class*="tabComboBox"], div[class*="filter"], select, div[role="button"]');
                elements.forEach(el => {{
                    const text = el.textContent || el.getAttribute('title') || el.getAttribute('aria-label') || '';
                    if (text.trim()) {{
                        filters.push({{
                            text: text.trim(),
                            tagName: el.tagName,
                            className: el.className
                        }});
                    }}
                }});
                return filters;
            }}
        """)
        
        # Look for chart data
        chart_data = await page.evaluate("""
            () => {{
                const charts = [];
                const elements = document.querySelectorAll('div[class*="tab-viz"], svg, canvas, div[class*="chart"]');
                elements.forEach(el => {{
                    const text = el.textContent || '';
                    if (text.trim()) {{
                        charts.push({{
                            text: text.trim(),
                            tagName: el.tagName,
                            className: el.className
                        }});
                    }}
                }});
                return charts;
            }}
        """)
        
        # Look for specific program count data
        program_counts = await page.evaluate("""
            () => {{
                const counts = [];
                const elements = document.querySelectorAll('div, span, td, th');
                elements.forEach(el => {{
                    const text = el.textContent || '';
                    const match = text.match(/([A-Za-z\\s]+):\\s*(\\d+)/);
                    if (match) {{
                        counts.push({{
                            college: match[1].trim(),
                            count: match[2],
                            fullText: text.trim()
                        }});
                    }}
                }});
                return counts;
            }}
        """)
        
        result = {{
            "title": title,
            "text_content": text_content,
            "filters": filter_elements,
            "charts": chart_data,
            "program_counts": program_counts,
            "question": "{question}",
            "url": page.url
        }}
        
        await browser.close()
        await playwright.stop()
        
        return result
        
    except Exception as e:
        return {{"error": str(e)}}

# Run the analysis
result = asyncio.run(analyze_dashboard())
print(json.dumps(result))
'''
            
            # Write script to temporary file
            script_path = "/tmp/tableau_analysis.py"
            with open(script_path, 'w') as f:
                f.write(script_content)
            
            # Run the script with much longer timeout for Tableau loading
            result = subprocess.run([sys.executable, script_path], 
                                  capture_output=True, text=True, timeout=300)
            
            logging.info(f"Script return code: {result.returncode}")
            logging.info(f"Script stdout: {result.stdout[:500]}...")  # First 500 chars
            logging.info(f"Script stderr: {result.stderr[:500]}...")  # First 500 chars
            
            if result.returncode == 0:
                if result.stdout.strip():
                    try:
                        return json.loads(result.stdout)
                    except json.JSONDecodeError as e:
                        logging.error(f"JSON decode error: {e}")
                        logging.error(f"Raw stdout: {result.stdout}")
                        return {"error": f"Invalid JSON output: {result.stdout[:200]}"}
                else:
                    return {"error": "Script returned empty output"}
            else:
                return {"error": f"Script failed with return code {result.returncode}: {result.stderr}"}
                
        except Exception as e:
            logging.error(f"Failed to run Playwright script: {e}")
            return {"error": str(e)}
    
    def analyze_dashboard_data(self, question, data):
        """Analyze the extracted data and generate insights"""
        try:
            # Handle truncated questions by expanding common patterns
            expanded_question = self.expand_truncated_question(question)
            logging.info(f"Original question: '{question}' -> Expanded: '{expanded_question}'")
            
            # Extract entities from expanded question
            entities = self.extract_entities_from_question(expanded_question.lower())
            
            # Parse text content for relevant information
            text_content = data.get("text_content", "")
            filters = data.get("filters", [])
            charts = data.get("charts", [])
            program_counts = data.get("program_counts", [])
            
            # Look for count/number questions
            response_parts = []
            
            if "how many" in expanded_question.lower() or "count" in expanded_question.lower():
                # First try to find specific college counts
                entities = self.extract_entities_from_question(expanded_question.lower())
                college_name = entities.get('location', '')
                
                if college_name and program_counts:
                    # Look for the specific college in program counts
                    for count_data in program_counts:
                        if college_name.lower() in count_data['college'].lower():
                            response_parts.append(f"🔢 **Answer: {count_data['count']} programs at {college_name}**")
                            break
                    else:
                        # If specific college not found, show all counts
                        if program_counts:
                            counts_text = ", ".join([f"{pc['college']}: {pc['count']}" for pc in program_counts[:5]])
                            response_parts.append(f"🔢 **Program counts:** {counts_text}")
                        else:
                            response_parts.append("🔢 No specific count found in the data")
                else:
                    # Fallback to extracting numbers from text content
                    import re
                    numbers = re.findall(r'\d+', text_content)
                    large_numbers = [n for n in numbers if int(n) >= 10]
                    
                    if large_numbers:
                        main_answer = max(large_numbers, key=int)
                        response_parts.append(f"🔢 **Answer: {main_answer}**")
                    else:
                        response_parts.append("🔢 No specific count found in the data")
            
            # Add filter information
            if filters:
                filter_names = [f["text"][:50] for f in filters[:5]]  # Limit length
                response_parts.append(f"🔍 **Available filters:** {', '.join(filter_names)}")
            
            # Add chart information
            if charts:
                chart_info = [c["text"][:100] for c in charts[:3]]  # Limit length
                response_parts.append(f"📊 **Chart data:** {', '.join(chart_info)}")
            
            # Add entity-specific information
            for entity_type, entity_value in entities.items():
                if entity_value:
                    # Look for data containing this entity
                    relevant_data = []
                    for chart in charts:
                        if entity_value.lower() in chart["text"].lower():
                            relevant_data.append(chart["text"][:100])
                    
                    if relevant_data:
                        response_parts.append(f"🎯 **{entity_value} data:** {', '.join(relevant_data[:2])}")
            
            # Add general text insights
            if text_content:
                # Extract key phrases
                lines = [line.strip() for line in text_content.split('\n') if line.strip()]
                key_lines = [line for line in lines if len(line) > 10 and len(line) < 200][:5]
                if key_lines:
                    response_parts.append(f"📋 **Dashboard content:** {', '.join(key_lines)}")
            
            return "\n".join(response_parts) if response_parts else "Dashboard analysis completed successfully."
            
        except Exception as e:
            logging.error(f"Failed to analyze dashboard data: {e}")
            return f"Analysis error: {str(e)}"
    
    def expand_truncated_question(self, question):
        """Expand truncated questions to their likely full form"""
        question_lower = question.lower()
        
        # Common truncation patterns and their expansions
        expansions = {
            "show me data for bachelor": "show me data for bachelor's programs",
            "show me data for master": "show me data for master's programs", 
            "show me data for associate": "show me data for associate programs",
            "show me data for certificate": "show me data for certificate programs",
            "how many bachelor": "how many bachelor's programs",
            "how many master": "how many master's programs",
            "how many associate": "how many associate programs",
            "how many certificate": "how many certificate programs",
            "filter by college": "filter by college and show results",
            "filter by degree": "filter by degree level and show results",
            "filter by program": "filter by program type and show results",
            "compare data": "compare data across different categories",
            "show me trends": "show me trends in the data over time",
            "show me charts": "show me charts and visualizations",
            "show me graphs": "show me graphs and charts"
        }
        
        # Check for exact matches first
        for truncated, expanded in expansions.items():
            if question_lower == truncated:
                return expanded
        
        # Check for partial matches
        for truncated, expanded in expansions.items():
            if truncated in question_lower:
                return expanded
        
        # If no match found, return original question
        return question
    
    def extract_entities_from_question(self, question_lower):
        """Extract entities from question"""
        entities = {}
        import re
        
        # Extract location entities (colleges, universities, etc.)
        college_names = ['lehman', 'baruch', 'queens', 'brooklyn', 'hunter', 'city college', 'bronx', 'staten island']
        for college in college_names:
            if college in question_lower:
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

# Global agent instance
tableau_agent = TableauDashboardAgent()

@tool(description="Analyzes Tableau dashboard data by applying filters and extracting insights from charts")
def analyze_tableau_dashboard(question: str):
    """
    Analyzes a Tableau dashboard based on user questions.
    Applies appropriate filters and extracts data from charts.
    """
    try:
        logging.info(f"Analyzing dashboard for question: {question}")
        
        # Run Playwright analysis in separate process
        data = tableau_agent.run_playwright_script(question)
        
        if "error" in data:
            return {"error": data["error"]}
        
        # Analyze the data
        response = tableau_agent.analyze_dashboard_data(question, data)
        
        return {
            "question": question,
            "response": response,
            "dashboard_data": {
                "title": data.get("title", ""),
                "url": data.get("url", ""),
                "filters_found": len(data.get("filters", [])),
                "charts_found": len(data.get("charts", []))
            }
        }
        
    except Exception as e:
        logging.error(f"Failed to analyze dashboard: {e}")
        return {"error": str(e)}


def main():
    client = AgentClient(
        auth_type="api_key",
        profile="DEFAULT",
        region="us-chicago-1"
    )

    agent = Agent(
        client=client,
        agent_endpoint_id="ocid1.genaiagentendpoint.oc1.us-chicago-1.amaaaaaakjeknfqa7qqxtgjcc2fauk2mi6u6oadru5o4bkjkxjy5gzbapq5q",
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
    #main()
    analyze_tableau_dashboard("how many computer science bachelor's program at Lehman")
