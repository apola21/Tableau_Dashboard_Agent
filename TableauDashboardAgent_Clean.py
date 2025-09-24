import asyncio
import json
import logging
import os
import sys
import base64
import time
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
            print(f"Analyzing question: '{question}'")
            entities = self.extract_entities_from_question(question.lower())
            print(f" Extracted Entities: {entities}")
            
            #so lets map entities to filters
            filters_to_apply = {}
            if entities.get("degree"):
                filters_to_apply["Award Level"] = entities['degree']
                print(f"Found degree '{entities['degree']}' - will apply Award Level filter")
            if entities.get('award_name'):
                filters_to_apply["Award Name"] = entities['award_name']
                print(f"Found award '{entities['award_name']}' - will apply Award Name filter")
            if entities.get('location'):
                filters_to_apply["Reporting College"] = entities['location']
                print(f"Found college name '{entities['location']}' - will apply Reporting College filter")
            if entities.get('college type'):
                filters_to_apply["Reporting College Type"] = entities['college name']
                print(f"Found college name '{entities['college name']}' - will apply Reporting College filter")
            if entities.get('program'):
                filters_to_apply["Program Name"] = entities['program']
                print(f"Found program '{entities['program']}' - will apply Program Name filter")
            if entities.get('category'):
                filters_to_apply["STEM Category"] = entities['category']
                print(f"Found category '{entities['category']}' - will apply STEM Category filter")
            if entities.get('enrolled_college'):
                filters_to_apply["Enrolled College"] = entities['enrolled_college']
                print(f"Found enrolled college '{entities['enrolled_college']}' - will apply Enrolled College filter")
            if entities.get('college_type'):
                filters_to_apply["Reporting College Type"] = entities['college_type']
                print(f"Found college type '{entities['college_type']}' - will apply Reporting College Type filter")
            if entities.get('enrolled_college_type'):
                filters_to_apply["Enrolled College Type"] = entities['enrolled_college_type']
                print(f"Found enrolled college type '{entities['enrolled_college_type']}' - will apply Enrolled College Type filter")
            if entities.get('academic_plan'):
                filters_to_apply["Academic Plan"] = entities['academic_plan']
                print(f"Found academic plan '{entities['academic_plan']}' - will apply Academic Plan filter")
            if entities.get('cip_2digit'):
                filters_to_apply["CIP 2-Digit Title/Code"] = entities['cip_2digit']
                print(f"Found CIP 2-digit '{entities['cip_2digit']}' - will apply CIP 2-Digit Title/Code filter")
            if entities.get('cip_4digit'):
                filters_to_apply["CIP 4-Digit Title/Code"] = entities['cip_4digit']
                print(f"Found CIP 4-digit '{entities['cip_4digit']}' - will apply CIP 4-Digit Title/Code filter")
            if entities.get('cip_6digit'):
                filters_to_apply["CIP 6-Digit Title/Code"] = entities['cip_6digit']
                print(f"Found CIP 6-digit '{entities['cip_6digit']}' - will apply CIP 6-Digit Title/Code filter")
            if entities.get('sevis_eligible'):
                filters_to_apply["Extended SEVIS-eligible Prgm"] = entities['sevis_eligible']
                print(f"Found SEVIS eligibility '{entities['sevis_eligible']}' - will apply Extended SEVIS-eligible Prgm filter")
            
            print(f"Filters to apply: {filters_to_apply}")
            if not filters_to_apply:
                print("No filters found in question!")
                return

            for label, value_to_select in filters_to_apply.items():
                print(f"\n=== Applying Filter: {label} = {value_to_select} ===")
                
                # 1. Find the filter's title element - handle strict mode violations
                label_locator = page.locator(f'h3.FilterTitle:has-text("{label}")')
                count = await label_locator.count()
                
                if count == 0:
                    print(f"  -> Could not find filter with label '{label}'.")
                    return False
                elif count > 1:
                    print(f"  -> Found {count} filters with label '{label}', using first one")
                    label_locator = label_locator.first
            
                # 2. Find and click the dropdown arrow
                arrow_locator = label_locator.locator('xpath=./ancestor::div[contains(@class, "Title")]/following-sibling::div//span[@class="tabComboBoxButton"]')
                await arrow_locator.click()

                # 3. Wait for the filter options panel to become visible
                panel_locator = page.locator('div[role="listbox"][class*="tile"]')
                await panel_locator.wait_for(state="visible", timeout=10000)
                print("  -> Filter panel is open.")
            
                # 4. Deselect the "(All)" option
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
                
                # Try multiple selectors for the Apply button - based on actual HTML structure
                apply_button = None
                apply_selectors = [
                    'div.CFApplyButtonContainer button.apply',  # Most specific - exact structure
                    'button.tab-button.apply',                  # Button with apply class
                    'button[title="Apply"]',                    # Button with title attribute
                    'button:has-text("Apply")',                 # Button containing Apply text
                    'span.label:has-text("Apply")',             # Span with label class
                    'button[class*="apply"]'                     # Any button with apply in class
                ]
                
                print("  -> Looking for Apply button...")
                
                # Try to find Apply button - first in panel, then page level
                for selector in apply_selectors:
                    try:
                        # Try within the panel first
                        apply_button = panel_locator.locator(selector)
                        count = await apply_button.count()
                        if count > 0:
                            print(f"  -> Found Apply button in panel with selector: {selector}")
                            break
                        
                        # If not found in panel, try at page level
                        apply_button = page.locator(selector)
                        count = await apply_button.count()
                        if count > 0:
                            print(f"  -> Found Apply button on page with selector: {selector}")
                            break
                    except:
                        continue
                
                if apply_button and await apply_button.count() > 0:
                    # Try to click the Apply button
                    try:
                        await apply_button.click()
                        print("  -> Clicked 'Apply' in dropdown.")
                    except Exception as e:
                        print(f"  -> Regular click failed: {e}, trying dispatch_event")
                        try:
                            await apply_button.dispatch_event('click')
                            print("  -> Clicked 'Apply' with dispatch_event.")
                        except Exception as e2:
                            print(f"  -> Both click methods failed: {e2}")
                else:
                    print("  -> ERROR: Could not find Apply button with any selector")
                
                # 7. Wait for the panel to disappear (with fallback)
                try:
                    await panel_locator.wait_for(state="hidden", timeout=5000)
                    print("  -> Filter panel is closed.")
                except Exception as e:
                    print(f"  -> Panel didn't close automatically: {e}")
                    print("  -> Proceeding anyway...")
                    print("  -> Trying to close panel manually...")
                    await page.keyboard.press('Escape')
                    await page.wait_for_timeout(1000)
                
                # 8. Wait for dashboard to reload before applying next filter
                print("  -> Waiting for dashboard to reload...")
                await self.wait_for_dashboard_reload(page)
                print("  -> Dashboard reload completed.")
    
        except Exception as e:
            print(f"Error applying filters: {e}")
            print("Continuing with next steps...")





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
    
    async def capture_dashboard_screenshot(self, page, question):
        """Capture full-page screenshot after filters are applied for VLM analysis"""
        try:
            # Wait for dashboard to fully load after filters
            print("📸 Waiting for dashboard to stabilize before screenshot...")
            await page.wait_for_timeout(5000)
            
            # Ensure screenshots directory exists
            os.makedirs("screenshots", exist_ok=True)
            
            # Generate unique filename with timestamp
            timestamp = int(time.time())
            screenshot_path = f"screenshots/dashboard_{timestamp}.png"
            
            # Take full page screenshot
            print(f"📸 Capturing screenshot: {screenshot_path}")
            await page.screenshot(path=screenshot_path, full_page=True)
            
            # Convert to base64 for VLM processing
            with open(screenshot_path, "rb") as image_file:
                image_base64 = base64.b64encode(image_file.read()).decode('utf-8')
            
            print(f"Screenshot captured successfully: {screenshot_path}")
            print(f"Image size: {len(image_base64)} characters (base64)")
            
            return {
                "screenshot_path": screenshot_path,
                "image_base64": image_base64,
                "timestamp": timestamp
            }
            
        except Exception as e:
            print(f"Error capturing screenshot: {e}")
            return {"error": str(e)}

    async def analyze_dashboard(self, question):
        try:
            logging.info("Using Playwright to apply filters and extract data...")
        
            playwright = await async_playwright().start()
            browser = await playwright.chromium.launch(headless=False)
            page = await browser.new_page(viewport={"width": 1920, "height": 1080})
            page.set_default_timeout(60000)
        
            print(f"🌍 Navigating to: {self.dashboard_url}")
            await page.goto(self.dashboard_url, wait_until="load", timeout=60000)
            print("✅ Page loaded successfully")
            
            print("⏸️ Pausing for 3 seconds so we can see the browser...")
            await page.wait_for_timeout(3000)
    
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
            
            # Capture screenshot for VLM analysis
            screenshot_data = await self.capture_dashboard_screenshot(page, question)
    
            result = {
                "title": await page.title(),
                "screenshot_data": screenshot_data,
                "question": question,
                "url": page.url
            }

            # Adding a long pause so we can visually inspect the filtered dashboard.
            print("Pausing for 5 seconds to observe the results...")
            await page.wait_for_timeout(5000) # 5-second pause
            
            await browser.close()
            await playwright.stop()
        
            return result
        
        except Exception as e:
            logging.error(f"Failed to analyze dashboard: {e}")
            return {"error": str(e)}
    def analyze_dashboard_data(self, question, data):
        """Analyze the dashboard data and prepare for VLM processing"""
        try:
            # Handle truncated questions by expanding common patterns
            expanded_question = self.expand_truncated_question(question)
            logging.info(f"Original question: '{question}' -> Expanded: '{expanded_question}'")
            
            # Extract entities from expanded question
            entities = self.extract_entities_from_question(expanded_question.lower())
            
            # Get screenshot data for VLM analysis
            screenshot_data = data.get("screenshot_data", {})
            
            # Prepare context for VLM
            applied_filters = []
            if entities.get('degree'):
                applied_filters.append(f"Award Level: {entities['degree']}")
            if entities.get('location'):
                applied_filters.append(f"Reporting College: {entities['location']}")
            if entities.get('category'):
                applied_filters.append(f"STEM Category: {entities['category']}")
            if entities.get('program'):
                applied_filters.append(f"Program Name: {entities['program']}")
            if entities.get('delivery_format'):
                applied_filters.append(f"Program Delivery Format: {entities['delivery_format']}")
            
            filter_context = ", ".join(applied_filters) if applied_filters else "No filters applied"
            
            # Prepare response for VLM analysis
            response_parts = []
            
            # Add context about applied filters
            response_parts.append(f"📊 **Applied Filters:** {filter_context}")
            
            # Add screenshot information
            if screenshot_data and not screenshot_data.get("error"):
                response_parts.append(f"📸 **Screenshot captured:** {screenshot_data.get('screenshot_path', 'Unknown')}")
                response_parts.append("🤖 **Ready for VLM analysis** - Screenshot will be processed by OCI Vision")
            else:
                response_parts.append("❌ **Screenshot failed** - Will use fallback text analysis")
            
            # Add detected entities
            if entities:
                entity_summary = ", ".join([f"{k}: {v}" for k, v in entities.items() if v])
                response_parts.append(f"🔍 **Detected entities:** {entity_summary}")
            
            return "\n\n".join(response_parts)
            
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
        
                # Extract STEM category entities (specific academic fields)
        stem_categories = {
            'computer science': ['computer science', 'cs', 'computing'],
            'biology': ['biology', 'biological'],
            'chemistry': ['chemistry', 'chemical'],
            'engineering': ['engineering', 'engineer'],
            'mathematics': ['mathematics', 'math', 'mathematical'],
            'physics': ['physics', 'physical'],
            'statistics': ['statistics', 'statistical'],
            'technology': ['technology', 'tech'],
            'earth science': ['earth science', 'environmental', 'marine science'],
            'general science': ['general science', 'science']
        }
        
        for category, keywords in stem_categories.items():
            for keyword in keywords:
                if keyword in question_lower:
                    entities['category'] = category.title()
                    break
            if 'category' in entities:
                break
        
        # Extract specific program names (only if not already categorized as STEM)
        if 'category' not in entities:
            # Look for specific program names like "Business Administration", "Nursing", etc.
            specific_programs = ['business administration', 'nursing', 'psychology', 'education', 'social work', 'criminal justice']
            for program in specific_programs:
                if program in question_lower:
                    entities['program'] = program.title()
                    break
        # Extract additional entity types for all 15 filters
        
        # Extract award name entities
        award_patterns = ['bachelor of arts', 'bachelor of science', 'master of arts', 'master of science', 'associate of arts', 'associate of science']
        for award in award_patterns:
            if award in question_lower:
                entities['award_name'] = award.title()
                break
        
        # Extract delivery format entities
        delivery_patterns = {
            'online': ['online', 'distance', 'remote'],
            'hybrid': ['hybrid', 'blended'],
            'in-person': ['in-person', 'on-campus', 'campus', 'face-to-face']
        }
        for format_type, keywords in delivery_patterns.items():
            for keyword in keywords:
                if keyword in question_lower:
                    entities['delivery_format'] = format_type.title()
                    break
            if 'delivery_format' in entities:
                break
        
        # Extract enrolled college entities (separate from reporting college)
        if 'enrolled' in question_lower:
            # Look for college names after "enrolled"
            enrolled_pattern = r'enrolled.*?(?:at|in)\s+([a-z\s]+(?:college|university))'
            match = re.search(enrolled_pattern, question_lower)
            if match:
                entities['enrolled_college'] = match.group(1).title()
        
        # Extract college type entities
        college_type_patterns = {
            'community': ['community college', 'cc'],
            'senior': ['senior college', 'four-year'],
            'graduate': ['graduate school', 'graduate center']
        }
        for type_name, keywords in college_type_patterns.items():
            for keyword in keywords:
                if keyword in question_lower:
                    entities['college_type'] = type_name.title()
                    break
            if 'college_type' in entities:
                break
        
        # Extract academic plan entities
        academic_patterns = ['full-time', 'part-time', 'accelerated', 'evening', 'weekend']
        for plan in academic_patterns:
            if plan in question_lower:
                entities['academic_plan'] = plan.title()
                break
        
        # Extract CIP code entities
        cip_patterns = [
            (r'\b(\d{2})\b', 'cip_2digit'),
            (r'\b(\d{4})\b', 'cip_4digit'), 
            (r'\b(\d{6})\b', 'cip_6digit')
        ]
        for pattern, entity_key in cip_patterns:
            matches = re.findall(pattern, question_lower)
            if matches:
                entities[entity_key] = matches[0]
                break
        
        # Extract SEVIS eligibility entities
        if any(word in question_lower for word in ['sevis', 'international', 'f-1', 'visa']):
            entities['sevis_eligible'] = 'Yes'
        
        # Extract education credentials entities
        credential_patterns = {
            'teacher credentials': ['teacher credentials', 'teaching credentials'],
            'administration credentials': ['administration credentials', 'admin credentials'],
            'counseling credentials': ['counseling credentials', 'pps credentials'],
            'teacher aide': ['teacher aide', 'aide credentials']
        }
        for cred_type, keywords in credential_patterns.items():
            for keyword in keywords:
                if keyword in question_lower:
                    entities['education_credentials'] = cred_type.title()
                    break
            if 'education_credentials' in entities:
                break
        
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
