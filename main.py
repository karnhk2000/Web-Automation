import psycopg2
import configparser
from selenium import webdriver
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import re
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager

# ================= Load Database Config =================
config = configparser.ConfigParser()
config.read("config.ini")  # make sure this file has [postgresql] section

DB_CONFIG = {
    "host": config["postgresql"]["host"],
    "port": config["postgresql"]["port"],
    "database": config["postgresql"]["database"],
    "user": config["postgresql"]["username"],
    "password": config["postgresql"]["password"],
}

# Connect to PostgreSQL
conn = psycopg2.connect(**DB_CONFIG)
cursor = conn.cursor()

# Create table if not exists
cursor.execute("""
CREATE TABLE IF NOT EXISTS songs (
    song_name TEXT,
    lyrics TEXT
)
""")
conn.commit()

# ================= Selenium Part =================
# User input for search query
QUERY = input("Enter song name or lyrics to search: ")
WAIT_TIMEOUT = 30

# Setup Selenium WebDriver
options = webdriver.ChromeOptions()
options.add_argument("--disable-blink-features=AutomationControlled")
options.add_argument("--start-maximized")

driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)

try:
    # Step 1: Open Google
    driver.get("https://www.google.com")

    # Step 2: Search for lyrics
    search_box = WebDriverWait(driver, 10).until(
        EC.presence_of_element_located((By.NAME, "q"))
    )
    search_box.send_keys(QUERY)
    search_box.send_keys(Keys.RETURN)

    # Step 3: Wait for first result and click it
    first_h3 = WebDriverWait(driver, WAIT_TIMEOUT).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, "div#search a > h3"))
    )
    parent_link = first_h3.find_element(By.XPATH, "./ancestor::a[1]")
    href = parent_link.get_attribute("href")
    print(f"Opening first result: {href}")
    driver.get(href)

    # Step 4: Extract lyrics depending on site
    page_url = driver.current_url.lower()
    lyrics_text = ""

    if "genius.com" in page_url:
        print("Detected Genius lyrics page...")
        containers = WebDriverWait(driver, 10).until(
            EC.presence_of_all_elements_located((By.CSS_SELECTOR, "div[data-lyrics-container='true']"))
        )
        lyrics_text = "\n".join([c.text for c in containers])

    elif "azlyrics.com" in page_url:
        print("Detected AZLyrics page...")
        all_divs = driver.find_elements(By.CSS_SELECTOR, "div")
        for div in all_divs:
            if div.text.strip() and len(div.text.split()) > 20:
                lyrics_text = div.text
                break

    else:
        print("Unknown site, using generic fallback...")
        paragraphs = driver.find_elements(By.TAG_NAME, "p")
        lyrics_text = "\n".join([p.text for p in paragraphs if p.text.strip()])
    
    # Clean and prepare data
    NEW_QUERY = re.sub(r'\s*lyrics\s*', '', QUERY, flags=re.IGNORECASE).strip()
    NEW_QUERY = NEW_QUERY.capitalize()
    # Remove unwanted text from lyrics
    cleaned_lyrics = re.sub(r'^.*?(?=\[Verse 1\])', '', lyrics_text, flags=re.DOTALL)
    # Step 5: Save to Database
    if lyrics_text.strip():
        cursor.execute(
            "INSERT INTO songs (song_name, lyrics) VALUES (%s, %s)",
            (NEW_QUERY, cleaned_lyrics.strip())
        )
        conn.commit()
        print("✅ Lyrics saved to PostgreSQL successfully!")
    else:
        print("❌ No lyrics extracted, nothing saved.")

    # Step 6: Print lyrics
    print("\n" + "="*40)
    print("🎵 Extracted Lyrics:")
    print("="*40 + "\n")
    print(lyrics_text.strip() if lyrics_text else "❌ Could not extract lyrics.")
    print("\n" + "="*40)

finally:
    driver.quit()
    cursor.close()
    conn.close()
