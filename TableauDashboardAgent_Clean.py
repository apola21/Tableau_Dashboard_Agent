import asyncio
import json
import logging
import os
import sys
from playwright.async_api import async_playwright
from playwright.async_api import Page
from oci.addons.adk import AgentClient, Agent, tool

# Import configuration
import importlib.util
spec = importlib.util.spec_from_file_location("config_AGENT", "config_AGENT.py")
l_env = importlib.util.module_from_spec(spec)
spec.loader.exec_module(l_env)

# Setup logging
log_dir = os.path.dirname(l_env.LOG_PATH)
os.makedirs(log_dir, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(l_env.LOG_PATH),
        logging.StreamHandler()
    ]
)

class TableauDashboardAgent:
    def __init__(self):
        self.dashboard_url = l_env.TABLEAU_DASHBOARD_URL

    async def discover_all_filters(self, page: Page):
        """Discover all available filters using the correct, specific class name."""
        try:
            print("Discovering filters using selector 'div.tabComboBoxNameContainer'...")
        
            filters = await page.evaluate("""
                () => {
                    const filters = [];
                    // 1. Find all the dropdown boxes using the class you identified.
                    const dropdownElements = document.querySelectorAll('div.tabComboBoxNameContainer');
                
                    dropdownElements.forEach(el => {
                        let labelText = 'Unknown Label';
                    
                    // 2. The dropdown control is a few levels up and has the 'aria-labelledby' attribute.
                        const control = el.closest('[role="button"]');
                    
                        if (control) {
                            // 3. Get the ID of the label from the 'aria-labelledby' attribute.
                            const labelId = control.getAttribute('aria-labelledby');
                            if (labelId) {
                                // 4. Find the label element using its ID.
                                const labelEl = document.getElementById(labelId);
                                if (labelEl) {
                                    labelText = labelEl.textContent.trim();
                                }
                            }
                        }
                    
                        filters.push({
                            label: labelText,
                        currentValue: el.textContent.trim()
                        });
                    });
                    return filters;
                }
            """)
        
            print(f"✅ Found {len(filters)} filters:")
            for filter_info in filters:
                print(f"  - Label: {filter_info['label']}, Current Value: {filter_info['currentValue']}")
        
            return filters
        
        except Exception as e:
            print(f"Error discovering filters: {e}")
            return []
        
    

    async def apply_dynamic_filter(self, page, filter_name, filter_value):
        """Apply any filter dynamically using Playwright's built-in waiting"""
        try:
            print(f"Applying filter '{filter_name}' with value '{filter_value}'...")
            
            # Try to find the filter element with built-in waiting
            filter_locator = page.locator(f'div[class*="tabComboBox"]:has-text("{filter_name}")')
            
            if await filter_locator.count() == 0:
                filter_locator = page.locator(f'select[title*="{filter_name}"]')
            
            if await filter_locator.count() == 0:
                filter_locator = page.locator(f'div[role="button"]:has-text("{filter_name}")')
            
            if await filter_locator.count() > 0:
                # Check if it's a select element
                tag_name = await filter_locator.first.evaluate("el => el.tagName")
                if tag_name.lower() == 'select':
                    await filter_locator.first.select_option(label=filter_value)
                    print(f"Applied {filter_name} filter: {filter_value}")
                    return True
                
                # For Tableau dropdown elements
                else:
                    await filter_locator.first.click()
                    
                    # Wait for dropdown to appear and click option
                    option_locator = page.locator(f'div:has-text("{filter_value}")')
                    if await option_locator.count() == 0:
                        option_locator = page.locator(f'li:has-text("{filter_value}")')
                    
                    if await option_locator.count() > 0:
                        await option_locator.first.click()
                        print(f"Applied {filter_name} filter: {filter_value}")
                        return True
            
            print(f"Could not find or apply filter: {filter_name}")
            return False
            
        except Exception as e:
            print(f"Error applying filter {filter_name}: {e}")
            return False

    def parse_question_with_llm(self, question, available_filters):
        """Use LLM to parse question and determine which filters to apply"""
        try:
            # Create a prompt for the LLM
            filter_names = [f['text'] for f in available_filters]
            
            prompt = f"""
            Analyze this user question and determine which filters to apply from the available filters.
            
            User Question: "{question}"
            
            Available Filters: {filter_names}
            
            Return a JSON object with the filters to apply. For each filter, provide:
            - filter_name: The exact name from the available filters
            - filter_value: The value to select (infer from the question)
            
            Example:
            {{
                "filters_to_apply": [
                    {{"filter_name": "Award Level", "filter_value": "Bachelor's"}},
                    {{"filter_name": "College", "filter_value": "Lehman College"}}
                ]
            }}
            
            If no filters match the question, return: {{"filters_to_apply": []}}
            """
            
            # For now, use a simple rule-based approach as fallback
            # In production, you would call an LLM API here
            return self.parse_question_fallback(question, available_filters)
            
        except Exception as e:
            print(f"Error parsing question with LLM: {e}")
            return {"filters_to_apply": []}

    def parse_question_fallback(self, question, available_filters):
        """Fallback rule-based parsing when LLM is not available"""
        filters_to_apply = []
        question_lower = question.lower()
        
        # Extract entities from the question
        entities = self.extract_entities_from_question(question_lower)
        
        # Match entities with available filters
        for filter_info in available_filters:
            filter_name = filter_info['text'].lower()
            
            # Check for degree level matches
            if any(word in filter_name for word in ['award', 'level', 'degree']) and entities.get('degree'):
                filters_to_apply.append({
                    "filter_name": filter_info['text'],
                    "filter_value": entities['degree']
                })
            
            # Check for location matches
            elif any(word in filter_name for word in ['college', 'university', 'location', 'campus']) and entities.get('location'):
                filters_to_apply.append({
                    "filter_name": filter_info['text'],
                    "filter_value": entities['location']
                })
            
            # Check for category matches
            elif any(word in filter_name for word in ['category', 'type', 'field']) and entities.get('category'):
                filters_to_apply.append({
                    "filter_name": filter_info['text'],
                    "filter_value": entities['category']
                })
            
            # Check for program matches
            elif any(word in filter_name for word in ['program', 'subject', 'major']) and entities.get('program'):
                filters_to_apply.append({
                    "filter_name": filter_info['text'],
                    "filter_value": entities['program']
                })
        
        return {"filters_to_apply": filters_to_apply}

    async def apply_filters_based_on_question(self, page, question):
        """
            Finds a filter, deselects "(All)", selects the correct value, 
            and clicks the "Apply" button inside the dropdown.
        """
        try:
            # Simple NLU to get filter values from the question
            filters_to_apply = {}
            if "bachelor" in question.lower():
                filters_to_apply["Award Level"] = "Bachelor's"
            if "lehman" in question.lower():
                filters_to_apply["Reporting College"] = "Lehman"

            for label, value_to_select in filters_to_apply.items():
                print(f"Applying filter '{label}' with value '{value_to_select}'...")
            
                # 1. Find the filter's title element
                label_locator = page.locator(f'h3.FilterTitle:has-text("{label}")')
                if not await label_locator.count() > 0:
                    print(f"  -> Could not find filter with label '{label}'.")
                    continue
            
                # 2. Find and click the dropdown arrow
                arrow_locator = label_locator.locator('xpath=./ancestor::div[contains(@class, "Title")]/following-sibling::div//span[@class="tabComboBoxButton"]')
                await arrow_locator.click()

                # 3. Wait for the filter options panel to become visible
                panel_locator = page.locator('div[role="listbox"][class*="tile"]')
                await panel_locator.wait_for(state="visible", timeout=10000)
                print("  -> Filter panel is open.")
            
                # 4. Deselect the "(All)" option
                # This more precise locator finds the input directly associated with the "(All)" text
                all_checkbox = panel_locator.locator('div[role="checkbox"]:has(a[title="(All)"]) input')
                await all_checkbox.click()
                print("  -> Deselected '(All)'.")
            
                # --- Add a brief pause to allow the web page's JavaScript to react ---
                await page.wait_for_timeout(500)

                # 5. Select the desired value
                value_checkbox = panel_locator.locator(f'div[role="checkbox"]:has(a[title="{value_to_select}"]) input')
                await value_checkbox.click()
                print(f"  -> Selected '{value_to_select}'.")
            
                # --- Add another pause before looking for the Apply button ---
                await page.wait_for_timeout(500)
                apply_button = panel_locator.locator('button:has-text("Apply")')
                print("  -> Waiting for Apply button to become enabled...")
                await apply_button.wait_for(state="enabled", timeout=5000)

                # 6. Click the now-enabled "Apply" button INSIDE the panel
                await panel_locator.locator('button:has-text("Apply")').click()
                print("  -> Clicked 'Apply' in dropdown.")
                
                # 7. Wait for the panel to disappear
                await panel_locator.wait_for(state="hidden", timeout=5000)
                print("  -> Filter panel is closed.")
    
        except Exception as e:
            print(f"Error applying filters: {e}")





    async def click_apply_button(self, page):
        """Finds and clicks the Apply button."""
        try:
            print("Looking for 'Apply' button...")
            # Use the selector you found: a span with the class 'label' and text 'Apply'.
            apply_button_locator = page.locator('span.label:has-text("Apply")')

            if await apply_button_locator.count() > 0:
                await apply_button_locator.click()
                print("✅ 'Apply' button clicked.")
                return True
            else:
                print("Could not find 'Apply' button.")
                return False
            
        except Exception as e:
            print(f"Error clicking apply button: {e}")
            return False

    async def wait_for_dashboard_reload(self, page):
        """
        Waits for the dashboard to reload using a more reliable and resilient strategy.
        """
        try:
            print("Waiting for dashboard to reload...")
        
            # Use 'load' instead of 'networkidle'. This is more reliable for complex apps
            # like Tableau that may have continuous background network activity.
            # It waits for the page's main load event to fire.
            await page.wait_for_load_state('load', timeout=30000)
        
            print("Dashboard reload wait completed.")
        
        except Exception as e:
            # If the wait times out, don't crash the script.
            # Log a warning and proceed, as the dashboard may have loaded enough
            #for data extraction to still succeed.
            print(f"Warning: A timeout occurred during the reload wait, but the agent will proceed. Error: {e}")
    
    async def extract_targeted_data(self, page, question):
        """Extract only the data needed to answer the specific question"""
        try:
            question_lower = question.lower()
            
            # Determine what type of data to extract based on question
            if any(word in question_lower for word in ['how many', 'count', 'number']):
                # Extract KPI numbers and counts
                return await self.extract_kpi_data(page)
            
            elif any(word in question_lower for word in ['show', 'list', 'what', 'which']):
                # Extract list data
                return await self.extract_list_data(page)
            
            elif any(word in question_lower for word in ['compare', 'difference']):
                # Extract comparison data
                return await self.extract_comparison_data(page)
            
            else:
                # Extract general summary data
                return await self.extract_summary_data(page)
                
        except Exception as e:
            print(f"Error extracting targeted data: {e}")
            return {"error": str(e)}

    async def extract_kpi_data(self, page):
        """Extract KPI numbers and counts specifically"""
        try:
            kpi_data = await page.evaluate("""
                () => {
                    const kpis = [];
                    
                    // Look for large numbers that could be KPIs
                    const elements = document.querySelectorAll('div, span, td, th, h1, h2, h3');
                    elements.forEach(el => {
                        const text = el.textContent || '';
                        const numbers = text.match(/\\b\\d{1,4}\\b/g);
                        
                        if (numbers && numbers.length > 0) {
                            const num = parseInt(numbers[0]);
                            if (num >= 10 && num <= 9999) { // Reasonable KPI range
                                kpis.push({
                                    value: num,
                                    context: text.trim(),
                                    element: el.tagName
                                });
                            }
                        }
                    });
                    
                    // Look for specific patterns like "College: 123"
                    const patternElements = document.querySelectorAll('div, span, td, th');
                    patternElements.forEach(el => {
                        const text = el.textContent || '';
                        const match = text.match(/([A-Za-z\\s]+):\\s*(\\d+)/);
                        if (match) {
                            kpis.push({
                                label: match[1].trim(),
                                value: parseInt(match[2]),
                                context: text.trim(),
                                type: 'labeled_count'
                            });
                        }
                    });
                    
                    return kpis;
                }
            """)
            
            return {"kpi_data": kpi_data, "type": "kpi"}
            
        except Exception as e:
            print(f"Error extracting KPI data: {e}")
            return {"error": str(e)}

    async def extract_list_data(self, page):
        """Extract list/table data"""
        try:
            list_data = await page.evaluate("""
                () => {
                    const lists = [];
                    
                    // Look for table rows
                    const rows = document.querySelectorAll('tr, div[class*="row"]');
                    rows.forEach(row => {
                        const cells = row.querySelectorAll('td, th, div[class*="cell"]');
                        if (cells.length > 1) {
                            const rowData = Array.from(cells).map(cell => cell.textContent?.trim()).filter(text => text);
                            if (rowData.length > 0) {
                                lists.push({
                                    type: 'table_row',
                                    data: rowData
                                });
                            }
                        }
                    });
                    
                    // Look for list items
                    const listItems = document.querySelectorAll('li, div[class*="item"]');
                    listItems.forEach(item => {
                        const text = item.textContent?.trim();
                        if (text && text.length > 3 && text.length < 200) {
                            lists.push({
                                type: 'list_item',
                                data: text
                            });
                        }
                    });
                    
                    return lists;
                }
            """)
            
            return {"list_data": list_data, "type": "list"}
            
        except Exception as e:
            print(f"Error extracting list data: {e}")
            return {"error": str(e)}

    async def extract_comparison_data(self, page):
        """Extract data for comparisons"""
        try:
            comparison_data = await page.evaluate("""
                () => {
                    const comparisons = [];
                    
                    // Look for data that could be compared (multiple values)
                    const elements = document.querySelectorAll('div, span, td, th');
                    elements.forEach(el => {
                        const text = el.textContent || '';
                        const numbers = text.match(/\\b\\d+\\b/g);
                        
                        if (numbers && numbers.length >= 2) {
                            comparisons.push({
                                context: text.trim(),
                                values: numbers.map(n => parseInt(n)),
                                element: el.tagName
                            });
                        }
                    });
                    
                    return comparisons;
                }
            """)
            
            return {"comparison_data": comparison_data, "type": "comparison"}
            
        except Exception as e:
            print(f"Error extracting comparison data: {e}")
            return {"error": str(e)}

    async def extract_summary_data(self, page):
        """Extract general summary data"""
        try:
            summary_data = await page.evaluate("""
                () => {
                    const summary = [];
                    
                    // Look for key text elements
                    const elements = document.querySelectorAll('h1, h2, h3, div[class*="title"], div[class*="summary"]');
                    elements.forEach(el => {
                        const text = el.textContent?.trim();
                        if (text && text.length > 5 && text.length < 300) {
                            summary.push({
                                type: 'heading',
                                text: text,
                                element: el.tagName
                            });
                        }
                    });
                    
                    return summary;
                }
            """)
            
            return {"summary_data": summary_data, "type": "summary"}
            
        except Exception as e:
            print(f"Error extracting summary data: {e}")
            return {"error": str(e)}

    async def analyze_dashboard(self, question):
        try:
            logging.info("Using Playwright to apply filters and extract data...")
        
            playwright = await async_playwright().start()
            browser = await playwright.chromium.launch(headless=False)
            page = await browser.new_page(viewport={"width": 1920, "height": 1080})
            page.set_default_timeout(60000)
        
            await page.goto(self.dashboard_url, wait_until="load", timeout=60000)
    
            # 1. Wait for the main container to be ready.
            print("Waiting for Tableau container to be ready...")
            await page.wait_for_selector('div#centeringContainer', timeout=30000)
            print("Tableau container is ready.")
    
            # 2. Wait for the filter elements to render INSIDE the main page container.
            print("Waiting for filters to render on the page...")
            await page.wait_for_selector('div.tabComboBoxNameContainer', timeout=60000) # Increased timeout
            print("Filters have rendered.")

            # --- All actions now use the main 'page' object ---
        
            await self.discover_all_filters(page)
            await self.apply_filters_based_on_question(page, question)
            await self.click_apply_button(page)
            await self.wait_for_dashboard_reload(page)
            targeted_data = await self.extract_targeted_data(page, question)
    
            result = {
                "title": await page.title(),
                "targeted_data": targeted_data,
                "question": question,
                "url": page.url
            }

            # Adding a long pause so we can visually inspect the filtered dashboard.
            print("Pausing for 10 seconds to observe the results...")
            await page.wait_for_timeout(10000) # 10-second pause
            
            await browser.close()
            await playwright.stop()
        
            return result
        
        except Exception as e:
            logging.error(f"Failed to analyze dashboard: {e}")
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
async def analyze_tableau_dashboard(question: str):
    """
    Analyzes a Tableau dashboard based on user questions.
    Applies appropriate filters and extracts data from charts.
    """
    try:
        logging.info(f"Analyzing dashboard for question: {question}")
        
        # Run Playwright analysis directly
        data = await(tableau_agent.analyze_dashboard(question))
        
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
    main()
