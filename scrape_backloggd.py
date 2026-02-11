import requests
from bs4 import BeautifulSoup
import os
import re
import time
import argparse
import sys

try:
    import cloudscraper

    HAS_CLOUDSCRAPER = True
except ImportError:
    HAS_CLOUDSCRAPER = False

import requests
from bs4 import BeautifulSoup

OUTPUT_DIR = "content/games"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://backloggd.com/",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "same-origin",
    "Sec-Fetch-User": "?1",
    "Cache-Control": "max-age=0",
}

STATUS_URLS = {
    "played": "played",
    "playing": "playing",
    "backlog": "backlog",
    "wishlist": "wishlist",
    "shelved": "shelved",
    "abandoned": "abandoned",
    "retired": "retired",
}

STATUS_MAPPING = {
    "played": "Completed",
    "playing": "Playing",
    "backlog": "Backlog",
    "wishlist": "Wishlist",
    "shelved": "Shelved",
    "abandoned": "Abandoned",
    "retired": "Retired",
}


def clean_slug(title):
    """Converts a title into a folder-safe slug."""
    slug = re.sub(r"[^\w\s-]", "", title).lower()
    slug = re.sub(r"[\s]+", "-", slug)
    return slug


def normalize_title(title):
    """Normalized title for matching (lowercase, no special chars)."""
    return re.sub(r"[^a-zA-Z0-9]", "", title).lower()


def escape_yaml(text):
    """Escapes text for YAML frontmatter."""
    if not text:
        return ""
    text = str(text).replace('"', '\\"')
    return f'"{text}"'


def get_star_rating(style_str):
    """Extracts rating from style string like 'width: 80%'."""
    if not style_str:
        return 0
    try:
        match = re.search(r"width:\s*([\d\.]+)%", style_str)
        if match:
            width = float(match.group(1))
            return width / 20.0
    except Exception as e:
        print(f"  [Warning] Could not parse rating style '{style_str}': {e}")
    return 0


def create_scraper(cookie=None):
    """Creates a CloudScraper session if available, else standard Session."""
    if HAS_CLOUDSCRAPER:
        s = cloudscraper.create_scraper()
    else:
        s = requests.Session()

    s.headers.update(HEADERS)
    if cookie:
        s.headers.update({"Cookie": cookie})
    return s


def fetch_page(session, url):
    """Fetches a page using the provided session."""
    print(f"Fetching: {url}")
    try:
        response = session.get(url)
        response.raise_for_status()
        time.sleep(1.5)

        if response.encoding is None:
            response.encoding = "utf-8"

        return BeautifulSoup(response.text, "html.parser")
    except Exception as e:
        print(f"Error fetching {url}: {e}")
        if "403" in str(e):
            print("\n!!! 403 FORBIDDEN ERROR DETECTED !!!")
            print("Backloggd is blocking the script. Try these steps:")
            print("1. Install cloudscraper: pip install cloudscraper")
            print("2. OR provide your browser cookie:")
            print(
                '   python3 scrape_backloggd.py [username] --cookie "your_cookie_string_here"'
            )
            print(
                "   (Get cookie from F12 -> Network -> Refresh Page -> Request Headers -> Cookie)\n"
            )
        return None


def scrape_games_by_status(session, username, status_slug):
    """Scrapes all games for a specific status category."""
    games = {}
    page = 1
    base_url = f"https://backloggd.com/u/{username}/games/added:desc/type:{status_slug}"

    last_page_hash = None

    while True:
        url = f"{base_url}?page={page}"
        soup = fetch_page(session, url)

        if not soup:
            break

        page_title = "No Title"
        if soup.title and soup.title.string:
            page_title = soup.title.string.strip()

        print(f"  [Debug] Page Title: {page_title}")

        if "Just a moment" in page_title or "Attention Required" in page_title:
            print(
                "  [Error] Cloudflare challenge detected! Your cookie might be invalid or expired."
            )
            break

        if "Login" in page_title:
            print("  [Error] Redirected to Login. Your cookie is invalid.")
            break

        game_entries = soup.select(".rating-hover")
        if not game_entries:
            game_entries = soup.select(".game-cover")

        if not game_entries:
            print("  [Debug] No game entries found on this page.")
            break

        current_page_hash = hash(str(game_entries))
        if current_page_hash == last_page_hash:
            print("  Reached end of list (duplicate content detected).")
            break
        last_page_hash = current_page_hash

        print(f"  Found {len(game_entries)} games on page {page}...")

        for entry in game_entries:
            title_div = entry.select_one(".game-text-centered")
            if not title_div:
                continue
            title = title_div.get_text(strip=True)

            if len(games) < 3:
                print(f"  [Debug] Found game: '{title}'")

            rating = 0
            cover_div = entry.select_one(".game-cover")
            if cover_div and cover_div.has_attr("data-rating"):
                try:
                    rating = float(str(cover_div["data-rating"])) / 2.0
                except:
                    pass

            if rating == 0:
                stars_el = entry.select_one(".stars-top")
                if stars_el and stars_el.has_attr("style"):
                    rating = get_star_rating(stars_el["style"])

            if len(games) < 3:
                print(f"  [Debug]   Rating: {rating}")

            cover_url = ""
            img = entry.select_one("img")
            if img:
                cover_url = img.get("src", "")

            games[title] = {
                "title": title,
                "status": STATUS_MAPPING.get(status_slug, "Completed"),
                "rating": rating,
                "cover_url": cover_url,
                "review": "",
                "date": time.strftime("%Y-%m-%d"),
                "platform": "PC",
            }

        page += 1

    return games


def scrape_reviews(session, username):
    """Scrapes reviews to attach text to games."""
    reviews = {}
    page = 1
    base_url = f"https://backloggd.com/u/{username}/reviews"

    print("\nStarting Review Scrape...")

    last_page_hash = None

    while True:
        url = f"{base_url}?page={page}"
        soup = fetch_page(session, url)

        if not soup:
            break

        review_cards = soup.select(".review-card")
        if not review_cards:
            review_cards = soup.select(".review")

        if not review_cards:
            break

        current_page_hash = hash(str(review_cards))
        if current_page_hash == last_page_hash:
            print("  Reached end of reviews (duplicate content detected).")
            break
        last_page_hash = current_page_hash

        print(f"  Found {len(review_cards)} reviews on page {page}...")

        for card in review_cards:
            title_sibling = card.find_previous_sibling(class_="game-name")
            title = ""

            if title_sibling:
                title_el = title_sibling.select_one("h3")
                if title_el:
                    title = title_el.get_text(strip=True)

            if not title:
                game_link = card.select_one(".card-header a[href^='/games/']")
                if game_link:
                    title = game_link.get_text(strip=True)

            if not title:
                print("  [Warning] Could not find game title for a review card.")
                continue

            if len(reviews) < 3:
                print(f"  [Debug] Found review for: '{title}'")

            review_text = ""
            body = card.select_one(".review-body")
            if body:
                text_el = body.select_one(".card-text")
                if text_el:
                    for br in text_el.find_all("br"):
                        br.replace_with("\n")
                    review_text = text_el.get_text(strip=True)
                else:
                    review_text = body.get_text("\n", strip=True)
            else:
                body = card.select_one(".card-body")
                if body:
                    review_text = body.get_text("\n", strip=True)

            review_date = ""
            date_el = card.select_one("time")
            if date_el and date_el.has_attr("datetime"):
                dt_val = date_el["datetime"]
                if isinstance(dt_val, list):
                    dt_val = dt_val[0]
                review_date = str(dt_val).split("T")[0]
            elif date_el:
                review_date = date_el.get_text(strip=True)

            platform = "PC"
            plat_el = card.select_one(".review-platform")
            if plat_el:
                platform = plat_el.get_text(strip=True)

            reviews[title] = {
                "text": review_text,
                "date": review_date,
                "platform": platform,
            }

        page += 1

    return reviews


def parse_cookie_file(file_path):
    """Parses a Netscape/Mozilla cookie file into a cookie string."""
    cookies = []
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            for line in f:
                if line.startswith("#") or not line.strip():
                    continue
                parts = line.strip().split("\t")
                if len(parts) >= 7:
                    name = parts[5]
                    value = parts[6]
                    cookies.append(f"{name}={value}")
        return "; ".join(cookies)
    except Exception as e:
        print(f"Error parsing cookie file: {e}")
        return None


def main():
    print("--- Backloggd Scraper & Importer ---")

    parser = argparse.ArgumentParser(description="Scrape Backloggd games and reviews.")
    parser.add_argument("username", help="Your Backloggd username")
    parser.add_argument(
        "--cookie",
        help="Browser cookie string OR path to cookies.txt file",
        default=None,
    )

    args = parser.parse_args()
    username = args.username

    cookie_val = args.cookie
    if cookie_val and os.path.isfile(cookie_val):
        print(f"Reading cookies from file: {cookie_val}")
        cookie_val = parse_cookie_file(cookie_val)

    if not HAS_CLOUDSCRAPER and not cookie_val:
        print("Note: 'cloudscraper' module not found. Using standard requests.")
        print("If you get 403 errors, install cloudscraper or use --cookie.\n")

    session = create_scraper(cookie_val)
    all_games = {}

    for status_key in STATUS_URLS.keys():
        print(f"\nScraping '{status_key}' games...")
        games = scrape_games_by_status(session, username, status_key)
        all_games.update(games)

    print(f"\nTotal games found: {len(all_games)}")

    found_reviews = scrape_reviews(session, username)

    normalized_map = {normalize_title(t): t for t in all_games.keys()}

    print(f"\nNormalized map created with {len(normalized_map)} entries.")
    sample_keys = list(normalized_map.keys())[:3]
    for k in sample_keys:
        print(f"  [Debug Map] '{k}' -> '{normalized_map[k]}'")

    matches = 0
    for review_title, review_data in found_reviews.items():
        norm_review_title = normalize_title(review_title)
        real_title = normalized_map.get(norm_review_title)

        review_text = review_data["text"]
        review_date = review_data["date"]

        if real_title:
            if matches < 3:
                print(
                    f"  [Debug] Match! Review '{review_title}' -> Game '{real_title}'"
                )
            all_games[real_title]["review"] = review_text
            if review_date:
                all_games[real_title]["date"] = review_date
            if review_data.get("platform"):
                all_games[real_title]["platform"] = review_data["platform"]
            matches += 1
        else:
            print(
                f"  [Warning] NO MATCH for review '{review_title}' (norm: '{norm_review_title}'). Adding as new game."
            )
            all_games[review_title] = {
                "title": review_title,
                "status": "Completed",
                "rating": 0,
                "cover_url": "",
                "review": review_text,
                "date": review_date if review_date else time.strftime("%Y-%m-%d"),
                "platform": review_data.get("platform", "PC"),
            }
            normalized_map[norm_review_title] = review_title
            matches += 1

    print(f"\nMatched {matches} reviews to games.")

    print(f"\nGenerating content in '{OUTPUT_DIR}'...")
    if not os.path.exists(OUTPUT_DIR):
        os.makedirs(OUTPUT_DIR)

    for title, data in all_games.items():
        slug = clean_slug(title)
        game_dir = os.path.join(OUTPUT_DIR, slug)

        if not os.path.exists(game_dir):
            os.makedirs(game_dir)

        cover_field = (
            f'cover_image: "{data["cover_url"]}"'
            if data["cover_url"]
            else 'cover_image: ""'
        )

        game_date = data.get("date", time.strftime("%Y-%m-%d"))

        md_content = f"""---
title: {escape_yaml(data["title"])}
date: {game_date}
draft: false
rating: {data["rating"]}
platform: {escape_yaml(data.get("platform", "PC"))}
completion_status: {escape_yaml(data["status"])}
tags: []
{cover_field}
---

{data["review"]}
"""
        with open(os.path.join(game_dir, "index.md"), "w", encoding="utf-8") as f:
            f.write(md_content)

    print("\nDone! Run 'hugo serve' to view your site.")


if __name__ == "__main__":
    main()
