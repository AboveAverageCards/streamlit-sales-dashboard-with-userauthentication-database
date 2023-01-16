from bs4 import BeautifulSoup
from lxml import html
import streamlit as st
import pandas as pd
import requests
import math
import time
import re
import database as db
import streamlit_authenticator as stauth

st.set_page_config(page_title = 'Above Average Cards',page_icon="🔬",layout='wide')

# --------USER AUTHENTICATION----------------

users = db.fetch_all_users()

names = [user["name"] for user in users]
usernames = [user["key"] for user in users]
hashed_passwords = [user["password"] for user in users]

authenticator = stauth.Authenticate(names, usernames, hashed_passwords,"above_average_cards", "cards_cookie", cookie_expiry_days=30)

name, authentication_status, username = authenticator.login("Login", "main")

if authentication_status == False:
 st.error('Username/password is incorrect')
if authentication_status == None:
 st.warning('Please enter your username and password')

if authentication_status:
    authenticator.logout("Logout", "sidebar")
    psa_pop, psa_url, app_run, dataset, download, sci_pricing, app_run2, prices = [st.container() for _ in range(8)]

    with psa_pop:
        st.header('Input PSA Link Below')
        
        set_url1 = st.text_input('https://www.psacard.com/pop/',placeholder='ex. https://www.psacard.com/pop/soccer-cards/2014/panini-prizm-world-cup/183170')
        sel_col2, disp_col2 = st.columns(2)
        card_pop = sel_col2.number_input('Specify Minimum Card Pop (Optional):',0)
        avg_grade = disp_col2.number_input('Specify Minimum Average Grade (Optional):',0.00)
        player_name = st.text_input('Name of Specifc Player as it Appears in PSA Pop Report (Optional):')


    #PSA pop calculations app ------------------------------------------------------------------------------------------------------------------------------------------------------------------------
    with app_run:
        
        col1, col2, col3 = st.columns(3)
        with col1:
            col1 = st.button("Click here to run PSA Scrape")

        if col1:
            try:
                set_req = requests.get(set_url1)

                # Parse the HTML content of the website
                soup_title = html.fromstring(set_req.content)

                # Find the desired element using its CSS selector
                set_title = soup_title.xpath("//html/body/main/div[2]/div/h1/text()")
                full_title = set_title[0] + ' | '
                set1 = str(full_title+set_url1)

                psa_urls = [set1]

                PAGE_MAX = 300
                POP_URL_BASE = "https://www.psacard.com/Pop/GetSetItems"
                EXAMPLE_URL = "https://www.psacard.com/pop/baseball-cards/2018/topps-update/161401"

                class PsaPopReport:
                    def __init__(self, pop_url, set_name):
                        self.pop_url = pop_url
                        self.set_name = set_name

                    def scrape(self):
                        print("collecting data for {}".format(self.set_name))

                        # Pull the set ID off the input url
                        try:
                            set_id = int(self.pop_url.split("/")[-1])
                        except:
                            print("Input URL should end in a numeric value, it should look like this: {}".format(EXAMPLE_URL))
                            return None

                        # Get json data for input set
                        sess = requests.Session()
                        sess.mount("https://", requests.adapters.HTTPAdapter(max_retries=5))
                        form_data = {
                            "headingID": str(set_id),
                            "categoryID": "20019",
                            "draw": 1,
                            "start": 0,
                            "length": 500,
                            "isPSADNA": "false"
                        }

                        try:
                            json_data = self.post_to_url(sess, form_data)
                        except Exception as err:
                            print("Error pulling data for {}, with error: {}".format(self.set_name, err))
                        cards = json_data["data"]

                        # If there's more than PAGE_MAX results, keep calling the scrape url until we have all of the card records
                        total_cards = json_data["recordsTotal"]
                        if total_cards > PAGE_MAX:
                            additional_pages = math.ceil((total_cards - PAGE_MAX) / PAGE_MAX)
                            for i in range(additional_pages):
                                curr_page = i + 1
                                form_data = {
                                    "headingID": str(set_id),
                                    "categoryID": "20019",
                                    "draw": curr_page + 2,
                                    "start": PAGE_MAX * curr_page,
                                    "length": PAGE_MAX,
                                    "isPSADNA": "false"
                                }

                                json_data = self.post_to_url(sess, form_data)
                                cards += json_data["data"]

                        # Create a dataframe
                        df = pd.DataFrame(cards[1:])
                        df = df.drop_duplicates(keep='first')
                        try:
                            df['Set'] = set_title[0]

                            # Remove unnecessary columns
                            columns_to_drop = ['Grade1Q','Grade2Q','Grade3Q', 'Grade4Q', 'Grade5Q', 'Grade6Q', 'Grade7Q', 'Grade8Q', 'Grade9Q','Grade1_5Q','CardNumberSort','GradeN0','HalfGradeTotal','QualifiedGradeTotal']
                            df.drop(columns_to_drop, axis=1, inplace=True)

                            # Add grade chances, expected grade
                            grade_cols = ['Grade10', 'Grade9', 'Grade8_5', 'Grade8', 'Grade7_5', 'Grade7', 'Grade6_5', 'Grade6', 'Grade5_5', 'Grade5', 'Grade4_5', 'Grade4', 'Grade3_5', 'Grade3', 'Grade2_5', 'Grade2', 'Grade1_5', 'Grade1']
                            df[['PSA_{}'.format(col.split('Grade')[1]) for col in grade_cols]] = df[grade_cols].div(df['Total'], axis=0)

                            # Add 'Avg_Grade' column
                            df['Avg_Grade'] = (10*df['PSA_10'])+(9*df['PSA_9'])+(8.5*df['PSA_8_5'])+(8*df['PSA_8'])+(7.5*df['PSA_7_5'])+(7*df['PSA_7'])+(6.5*df['PSA_6_5'])+(6*df['PSA_6'])+(5.5*df['PSA_5_5'])+(5*df['PSA_5'])+(4.5*df['PSA_4_5'])+(4*df['PSA_4'])+(3.5*df['PSA_3_5'])+(3*df['PSA_3'])+(2.5*df['PSA_2_5'])+(2*df['PSA_2'])+(1.5*df['PSA_1_5'])+(1*df['PSA_1'])
                            df['Avg_Grade'] = round(df['Avg_Grade'], 2)
                        

                            # Multiply the chances by 100, format them as percentages and add '%' sign
                            grade_chances = df.filter(like='PSA_').mul(100).applymap("{0:.1f}%".format)
                            df = pd.concat([df,grade_chances], axis=1)

                            # Write in base for blank variety types 
                            df.loc[df["Variety"] == "", "Variety"] = 'Base'                 

                            df = df.sort_values(by='Avg_Grade', ascending=False)[['Set','CardNumber','SubjectName','Variety','Avg_Grade','Total']]

                            # if not looking for specific player
                            if 'data_history' not in st.session_state:
                                st.session_state.data_history = 'data_history'
                            st.session_state.data_history = df
                            if 'set_title' not in st.session_state:
                                st.session_state.set_title = 'set_title'
                            st.session_state.set_title = set_title[0]

                            # if not looking for specific player            
                            if len(player_name) == 0:
                                st.session_state.data_history = df

                            else:
                                df = df[df['SubjectName'] == player_name]
                                st.session_state.data_history = df

                    
                        except:
                            st.text("No PSA Set to Scrape")

                    def post_to_url(self, session, form_data):
                        r = session.post(POP_URL_BASE, data=form_data)
                        r.raise_for_status()
                        json_data = r.json()
                        time.sleep(3)
                        return json_data

                if __name__ == '__main__':
                    for url in psa_urls:
                        input_url = url
                        set_name = url.split("/")[-1]
                        report = PsaPopReport(input_url, set_name)
                        report.scrape()
            except:
                st.text("No PSA Set to Scrape")            

    try:
        with dataset:
            df = pd.DataFrame()
            df = st.session_state.data_history
            df = df[df['Avg_Grade']>avg_grade]
            df = df[df['Total']>card_pop]
            if len(player_name) == 0:
                st.write(df)
            else:
                df = df[df['SubjectName'] == player_name]
                st.write(df)
        with download:
            set_name = str(st.session_state.set_title)
            def convert_df(df):
                return df.to_csv(index=False).encode('utf-8')
            csv = convert_df(df)
            st.download_button("Click to Download",csv,set_name+'.csv',"text/csv",key='download-csv') 
            
    except:
        pass


    # SCI portion ------------------------------------------------------------------------------------------------------------------------------------------------------------------------
    with sci_pricing:
        st.header('Input SCI Link Below')
        sci_url1 = st.text_input('https://www.sportscardinvestor.com/cards/',placeholder='ex. https://www.sportscardinvestor.com/cards/lionel-messi-soccer/2014-prizm-world-cup-base')

    with app_run2:
        if st.button("Calculate card price with SCI link"):

            try:
                # Scrape Card Title
                response = requests.get(sci_url1)

                tree = html.fromstring(response.content)

                # Find the element using the path
                element = tree.xpath("/html/body/div/div[3]/div[1]/div/div[2]/div[1]/h1")

                # Extract the text from the element
                sci_title = element[0].text if element else None
                sci_title = str.replace(sci_title,' Price Guide','')            

                # Scrape card prices
                stringpattern = '<.*?>'
                CLEANR = re.compile(stringpattern) 
                def Convert(string):
                    li = list(string.split('|'))
                    return li

                EXAMPLE_URL = "https://www.sportscardinvestor.com/cards/lionel-messi-soccer/2022-prizm-world-cup-blue"
                SCI_URL_BASE = "https://www.sportscardinvestor.com/cards/"

                html_content = requests.get(sci_url1).text
                soup = BeautifulSoup(html_content, 'html.parser')
                data = str(soup.find_all(class_="sci-ebay-grid sci-recentSales-grid sci-load-more"))

                links_regex = re.compile('((https?):((//www.ebay.com|//www.ha.com|//www.pwccmarketplace.com|//www.goldinauctions.com)|(\\\\))+([\w\d:#@%/;$()~_?\+-=\\\.&](#!)?)*)',re.DOTALL)
                links = re.findall(links_regex,data)

                cleanlinks = []
                for lnk in links:
                    cleanlinks.append(lnk[0])

                cleandata = Convert(re.sub(CLEANR,'',data).replace('\n','').replace('                        ','').replace('                    ','|').replace('comps $','').replace('$','|$').replace('SOLD ','|').replace('Load More','').replace('🔥','').replace('[','').replace(']',''))

                cleandata1 = [x for x in cleandata if x != '']

                cleanlinks1 = cleanlinks[0::2]


                title = cleandata1[0::3]
                price = cleandata1[1::3]
                date = cleandata1[2::3]
                ebaylink = cleanlinks1
                gradepull = []

                grade_dict = {"PSA 10": "PSA 10",
                            "PSA 9": "PSA 9",
                            "PSA 8": "PSA 8",
                            "PSA 7": "PSA 7",
                            "PSA 6": "PSA 6",
                            "PSA 5": "PSA 5",
                            "PSA 4": "PSA 4",
                            "PSA 3": "PSA 3",
                            "PSA 2": "PSA 2",
                            "PSA 1": "PSA 1",
                            "BGS 10": "BGS 10",
                            "BGS 9.5": "BGS 9.5",
                            "BGS 9": "BGS 9",
                            "BGS 8.5": "BGS 8.5",
                            "BGS 8": "BGS 8",
                            "BGS 7.5": "BGS 7.5",
                            "BGS 7": "BGS 7",
                            "BGS 6.5": "BGS 6.5",
                            "BGS 6": "BGS 6",
                            "BGS 5.5": "BGS 5.5",
                            "BGS 5": "BGS 5",
                            "BGS 4.5": "BGS 4.5",
                            "BGS 4": "BGS 4",
                            "BGS 3.5": "BGS 3.5",
                            "BGS 3": "BGS 3",
                            "BGS 2.5": "BGS 2.5",
                            "BGS 2": "BGS 2",
                            "BGS 1.5": "BGS 1.5",
                            "BGS 1": "BGS 1",
                            "SGC 10": "SGC 10",
                            "SGC 9.5": "SGC 9.5",
                            "SGC 9": "SGC 9",
                            "SGC 8.5": "SGC 8.5",
                            "SGC 8": "SGC 8",
                            "SGC 7.5": "SGC 7.5",
                            "SGC 7": "SGC 7",
                            "SGC 6.5": "SGC 6.5",
                            "SGC 6": "SGC 6",
                            "SGC 5.5": "SGC 5.5",
                            "SGC 5": "SGC 5",
                            "SGC 4.5": "SGC 4.5",
                            "SGC 4": "SGC 4",
                            "SGC 3.5": "SGC 3.5",
                            "SGC 3": "SGC 3",
                            "SGC 2.5": "SGC 2.5",
                            "SGC 2": "SGC 2",
                            "SGC 1.5": "SGC 1.5",
                            "SGC 1": "SGC 1",
                            }
                gradepull = [next((grade_dict.get(title) for title in grade_dict if title in val), "Raw") for val in title]

                df1 = pd.DataFrame()
                df1['Grade'] = gradepull

                df1['Price'] = price
                df1['Price'] = (pd.to_numeric(df1['Price'].str.replace('$','').str.replace(',',''), errors='coerce'))

                df1['Date Sold'] = date
                df1['eBay Link'] = ebaylink
                df1 = df1.fillna(0).drop_duplicates(subset=['Grade'],keep='first')

                if 'price_history' not in st.session_state:
                    st.session_state.price_history = 'price_history'
                st.session_state.price_history = df1
            except:
                if 'price_history' not in st.session_state:
                    st.session_state.price_history = 'price_history'
                st.session_state.price_history = "Error in SCI Link"

    try:
        with prices:
            st.subheader(sci_title)
            df_write = pd.DataFrame()
            df_write = st.session_state.price_history.sort_values(by='Price', ascending=False)
            st.write(df_write.style.format({'Price': '{:.2f}'}))

    except:
        pass
