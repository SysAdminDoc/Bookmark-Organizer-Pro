#!/usr/bin/env python3
"""Add top 5000 Tranco domains to default_categories.py.

Uses domain name heuristics, TLD analysis, and a curated mapping for
well-known sites to categorize domains without needing AI or web lookups.
"""

import sys
import zipfile
sys.path.insert(0, ".")

# Infrastructure/CDN/API domains that users don't bookmark
SKIP_DOMAINS = {
    # DNS/CDN/infrastructure
    "gtld-servers.net", "gstatic.com", "googleapis.com", "amazonaws.com",
    "cloudflare.com", "cloudflare.net", "akamai.net", "akamaized.net",
    "akadns.net", "akamaiedge.net", "edgesuite.net", "fastly.net",
    "cloudfront.net", "azureedge.net", "azurewebsites.net", "trafficmanager.net",
    "googleusercontent.com", "googlevideo.com", "googletagmanager.com",
    "googlesyndication.com", "googleadservices.com", "google-analytics.com",
    "doubleclick.net", "gstatic.com", "ggpht.com", "gvt1.com", "gvt2.com",
    "fbcdn.net", "facebook.net", "fbsbx.com", "fbcdn.com",
    "aaplimg.com", "mzstatic.com", "apple-dns.net",
    "msecnd.net", "msftncsi.com", "live.net", "windows.net",
    "windowsupdate.com", "office.net", "office.com",
    "s3.amazonaws.com", "elasticbeanstalk.com", "awsstatic.com",
    "verisign.com", "verisign.net", "icann.org", "iana.org",
    "root-servers.net", "ripn.net", "domaincontrol.com",
    "googledomains.com", "ntp.org", "arpa.net", "in-addr.arpa",
    "cloud.microsoft", "azure.com",
    # Tracking/ads
    "doubleclick.net", "googlesyndication.com", "googleadservices.com",
    "facebook.net", "fbsbx.com", "appsflyersdk.com", "appsflyer.com",
    "branch.io", "adjust.com", "kochava.com", "singular.net",
    "sentry.io", "segment.io", "segment.com", "mixpanel.com",
    "amplitude.com", "hotjar.com", "fullstory.com", "clarity.ms",
    "onesignal.com", "pushwoosh.com", "airship.com",
    "criteo.com", "criteo.net", "taboola.com", "outbrain.com",
    "pubmatic.com", "rubiconproject.com", "openx.com",
    "moatads.com", "doubleverify.com", "iasds01.com",
    # Hosting/platform infra (not the user-facing sites)
    "wpengine.com", "pantheon.io", "kinsta.cloud",
    "herokuapp.com", "vercel.app", "netlify.app",
    "wixsite.com", "squarespace.com", "weebly.com",
    "ghost.io", "substack.com", "medium.com",  # platform, not specific content
    # Email/messaging infra
    "sendgrid.net", "mailgun.net", "mailchimp.com", "mandrill.com",
    "constantcontact.com", "campaignmonitor.com",
    # Auth/SSO
    "auth0.com", "okta.com", "onelogin.com",
    # Other infra
    "recaptcha.net", "hcaptcha.com", "turnstile.com",
    "unpkg.com", "cdnjs.cloudflare.com", "jsdelivr.net",
    "bootstrapcdn.com", "fontawesome.com",
    "jquery.com", "reactjs.org",
    # Registrars (not bookmarkable content)
    "namecheap.com", "name.com", "enom.com", "dynadot.com",
    # Misc infra
    "ezviz7.com", "hicloudcam.com", "tuya.com",
    "whatsapp.net", "signal.org",
}

# Well-known domains -> category mapping (curated top sites)
KNOWN_SITES = {
    # Search engines
    "google.com": "Technology", "bing.com": "Technology", "yahoo.com": "Technology",
    "duckduckgo.com": "Technology", "baidu.com": "Technology",
    "yandex.ru": "Technology", "yandex.com": "Technology",
    "ecosia.org": "Technology", "startpage.com": "Technology",

    # Major platforms
    "facebook.com": "Social Media", "instagram.com": "Social Media",
    "twitter.com": "Social Media", "x.com": "Social Media",
    "pinterest.com": "Social Media", "snapchat.com": "Social Media",
    "reddit.com": "Forums", "quora.com": "Forums",
    "discord.com": "Forums", "telegram.org": "Social Media",
    "whatsapp.com": "Social Media", "messenger.com": "Social Media",
    "tumblr.com": "Social Media", "threads.net": "Social Media",

    # Video
    "youtube.com": "Video", "twitch.tv": "Video", "vimeo.com": "Video",
    "dailymotion.com": "Video", "tiktok.com": "Video",
    "bilibili.com": "Video", "nicovideo.jp": "Video",

    # News
    "cnn.com": "News", "bbc.com": "News", "bbc.co.uk": "News",
    "nytimes.com": "News", "washingtonpost.com": "News",
    "theguardian.com": "News", "reuters.com": "News",
    "apnews.com": "News", "nbcnews.com": "News",
    "foxnews.com": "News", "abcnews.go.com": "News",
    "cbsnews.com": "News", "usatoday.com": "News",
    "latimes.com": "News", "nypost.com": "News",
    "politico.com": "News", "thehill.com": "News",
    "axios.com": "News", "vox.com": "News",
    "huffpost.com": "News", "vice.com": "News",
    "buzzfeed.com": "News", "slate.com": "News",
    "salon.com": "News", "dailybeast.com": "News",
    "independent.co.uk": "News", "telegraph.co.uk": "News",
    "aljazeera.com": "News", "dw.com": "News",
    "france24.com": "News", "spiegel.de": "News",
    "lemonde.fr": "News", "elpais.com": "News",
    "corriere.it": "News", "asahi.com": "News",
    "mainichi.jp": "News", "timesofindia.indiatimes.com": "News",
    "ndtv.com": "News", "hindustantimes.com": "News",
    "scmp.com": "News", "straitstimes.com": "News",
    "abc.net.au": "News", "cbc.ca": "News",
    "globo.com": "News", "uol.com.br": "News",
    "rt.com": "News", "tass.com": "News",
    "kyodonews.net": "News", "jiji.com": "News",
    "haaretz.com": "News", "timesofisrael.com": "News",
    "cnbc.com": "News", "bloomberg.com": "News",

    # Technology / Tech News
    "theverge.com": "Technology", "techcrunch.com": "Technology",
    "wired.com": "Technology", "arstechnica.com": "Technology",
    "zdnet.com": "Technology", "cnet.com": "Technology",
    "engadget.com": "Technology", "tomshardware.com": "Technology",
    "anandtech.com": "Technology", "pcmag.com": "Technology",
    "macrumors.com": "Technology", "9to5mac.com": "Technology",
    "9to5google.com": "Technology", "slashdot.org": "Technology",
    "theregister.com": "Technology",

    # Software Development
    "github.com": "Software Development", "gitlab.com": "Software Development",
    "stackoverflow.com": "Software Development", "bitbucket.org": "Software Development",
    "dev.to": "Software Development", "hashnode.com": "Software Development",
    "hackernoon.com": "Software Development", "freecodecamp.org": "Software Development",
    "codecademy.com": "Education", "w3schools.com": "Education",
    "developer.mozilla.org": "Software Development",
    "npmjs.com": "Software Development", "pypi.org": "Software Development",
    "crates.io": "Software Development", "nuget.org": "Software Development",
    "packagist.org": "Software Development", "rubygems.org": "Software Development",
    "maven.org": "Software Development", "hub.docker.com": "Software Development",

    # Shopping / E-commerce
    "amazon.com": "Shopping", "amazon.co.uk": "Shopping",
    "amazon.de": "Shopping", "amazon.co.jp": "Shopping",
    "amazon.fr": "Shopping", "amazon.it": "Shopping",
    "amazon.es": "Shopping", "amazon.ca": "Shopping",
    "amazon.com.au": "Shopping", "amazon.in": "Shopping",
    "amazon.com.br": "Shopping", "amazon.com.mx": "Shopping",
    "ebay.com": "Shopping", "ebay.co.uk": "Shopping",
    "ebay.de": "Shopping", "etsy.com": "Shopping",
    "walmart.com": "Shopping", "target.com": "Shopping",
    "aliexpress.com": "Shopping", "alibaba.com": "Shopping",
    "wish.com": "Shopping", "temu.com": "Shopping",
    "shein.com": "Shopping", "rakuten.co.jp": "Shopping",
    "mercadolibre.com": "Shopping", "flipkart.com": "Shopping",
    "jd.com": "Shopping", "taobao.com": "Shopping",
    "tmall.com": "Shopping", "bestbuy.com": "Shopping",
    "costco.com": "Shopping", "homedepot.com": "Shopping",
    "lowes.com": "Shopping", "ikea.com": "Shopping",
    "wayfair.com": "Shopping", "newegg.com": "Shopping",
    "zappos.com": "Shopping", "nordstrom.com": "Shopping",
    "macys.com": "Shopping", "kohls.com": "Shopping",

    # Finance
    "paypal.com": "Finance", "stripe.com": "Finance",
    "chase.com": "Finance", "bankofamerica.com": "Finance",
    "wellsfargo.com": "Finance", "capitalone.com": "Finance",
    "americanexpress.com": "Finance", "discover.com": "Finance",
    "fidelity.com": "Finance", "vanguard.com": "Finance",
    "schwab.com": "Finance", "tdameritrade.com": "Finance",
    "robinhood.com": "Finance", "coinbase.com": "Finance",
    "binance.com": "Finance", "kraken.com": "Finance",
    "coinmarketcap.com": "Finance", "coingecko.com": "Finance",
    "nerdwallet.com": "Finance", "creditkarma.com": "Finance",
    "mint.com": "Finance", "sofi.com": "Finance",
    "wise.com": "Finance", "revolut.com": "Finance",
    "investopedia.com": "Finance",

    # Entertainment
    "netflix.com": "Entertainment", "hulu.com": "Entertainment",
    "disneyplus.com": "Entertainment", "hbomax.com": "Entertainment",
    "max.com": "Entertainment", "primevideo.com": "Entertainment",
    "crunchyroll.com": "Entertainment", "peacocktv.com": "Entertainment",
    "paramountplus.com": "Entertainment", "spotify.com": "Entertainment",
    "apple.com": "Technology", "music.apple.com": "Entertainment",
    "soundcloud.com": "Entertainment", "deezer.com": "Entertainment",
    "tidal.com": "Entertainment", "pandora.com": "Entertainment",
    "imdb.com": "Entertainment", "rottentomatoes.com": "Entertainment",
    "metacritic.com": "Entertainment", "letterboxd.com": "Entertainment",
    "fandom.com": "Entertainment", "genius.com": "Entertainment",

    # Gaming
    "steampowered.com": "Gaming", "store.steampowered.com": "Gaming",
    "epicgames.com": "Gaming", "gog.com": "Gaming",
    "ign.com": "Gaming", "gamespot.com": "Gaming",
    "pcgamer.com": "Gaming", "kotaku.com": "Gaming",
    "polygon.com": "Gaming", "roblox.com": "Gaming",
    "minecraft.net": "Gaming", "ea.com": "Gaming",
    "ubisoft.com": "Gaming", "playstation.com": "Gaming",
    "xbox.com": "Gaming", "nintendo.com": "Gaming",
    "nexusmods.com": "Gaming", "curseforge.com": "Gaming",

    # Health
    "webmd.com": "Health", "mayoclinic.org": "Health",
    "healthline.com": "Health", "nih.gov": "Health",
    "cdc.gov": "Health", "who.int": "Health",
    "medlineplus.gov": "Health", "drugs.com": "Health",
    "goodrx.com": "Health", "cvs.com": "Health",
    "walgreens.com": "Health",

    # Education
    "wikipedia.org": "Reference", "wikimedia.org": "Reference",
    "coursera.org": "Education", "udemy.com": "Education",
    "edx.org": "Education", "khanacademy.org": "Education",
    "duolingo.com": "Education", "quizlet.com": "Education",
    "chegg.com": "Education", "studocu.com": "Education",
    "scribd.com": "Education", "slideshare.net": "Education",
    "academia.edu": "Education", "researchgate.net": "Science",
    "scholar.google.com": "Science",

    # Science
    "nature.com": "Science", "sciencedirect.com": "Science",
    "springer.com": "Science", "wiley.com": "Science",
    "arxiv.org": "Science", "pubmed.ncbi.nlm.nih.gov": "Science",
    "nasa.gov": "Science", "space.com": "Science",
    "ieee.org": "Science",

    # Travel
    "booking.com": "Travel", "airbnb.com": "Travel",
    "expedia.com": "Travel", "tripadvisor.com": "Travel",
    "kayak.com": "Travel", "skyscanner.com": "Travel",
    "hotels.com": "Travel", "trivago.com": "Travel",
    "google.com/travel": "Travel", "maps.google.com": "Travel",

    # Food
    "doordash.com": "Food", "ubereats.com": "Food",
    "grubhub.com": "Food", "yelp.com": "Food",
    "allrecipes.com": "Food", "foodnetwork.com": "Food",

    # Real Estate
    "zillow.com": "Real Estate", "realtor.com": "Real Estate",
    "redfin.com": "Real Estate", "trulia.com": "Real Estate",
    "apartments.com": "Real Estate",

    # Government
    "irs.gov": "Government", "usa.gov": "Government",
    "whitehouse.gov": "Government", "state.gov": "Government",
    "congress.gov": "Government",

    # Careers
    "indeed.com": "Careers", "glassdoor.com": "Careers",
    "monster.com": "Careers", "ziprecruiter.com": "Careers",
    "linkedin.com": "Careers",

    # Productivity
    "notion.so": "Productivity", "trello.com": "Productivity",
    "asana.com": "Productivity", "monday.com": "Productivity",
    "slack.com": "Productivity", "zoom.us": "Productivity",
    "docs.google.com": "Productivity", "drive.google.com": "Productivity",
    "dropbox.com": "Productivity", "box.com": "Productivity",
    "evernote.com": "Productivity", "todoist.com": "Productivity",
    "canva.com": "Design", "figma.com": "Design",

    # AI
    "openai.com": "Artificial Intelligence", "claude.ai": "Artificial Intelligence",
    "anthropic.com": "Artificial Intelligence", "chatgpt.com": "Artificial Intelligence",
    "gemini.google.com": "Artificial Intelligence", "perplexity.ai": "Artificial Intelligence",
    "midjourney.com": "Artificial Intelligence", "huggingface.co": "Artificial Intelligence",

    # Cloud
    "aws.amazon.com": "Cloud Computing", "cloud.google.com": "Cloud Computing",
    "azure.microsoft.com": "Cloud Computing", "digitalocean.com": "Cloud Computing",
    "heroku.com": "Cloud Computing",

    # Cybersecurity
    "norton.com": "Cybersecurity", "mcafee.com": "Cybersecurity",
    "kaspersky.com": "Cybersecurity", "avast.com": "Cybersecurity",
    "malwarebytes.com": "Cybersecurity", "1password.com": "Cybersecurity",
    "bitwarden.com": "Cybersecurity", "lastpass.com": "Cybersecurity",
    "nordvpn.com": "Cybersecurity", "expressvpn.com": "Cybersecurity",
    "proton.me": "Cybersecurity", "protonmail.com": "Cybersecurity",

    # Weather
    "weather.com": "Weather", "accuweather.com": "Weather",
    "wunderground.com": "Weather", "weather.gov": "Weather",

    # Sports
    "espn.com": "Sports", "nba.com": "Sports",
    "nfl.com": "Sports", "mlb.com": "Sports",
    "fifa.com": "Sports", "uefa.com": "Sports",
    "premierleague.com": "Sports", "nhl.com": "Sports",
    "bbc.com/sport": "Sports",

    # Photography
    "unsplash.com": "Photography", "pexels.com": "Photography",
    "shutterstock.com": "Photography", "gettyimages.com": "Photography",
    "flickr.com": "Photography", "500px.com": "Photography",

    # Fashion
    "zara.com": "Fashion", "hm.com": "Fashion",
    "asos.com": "Fashion", "nike.com": "Fashion",
    "adidas.com": "Fashion",

    # Home
    "houzz.com": "Home", "bhg.com": "Home",
    "hgtv.com": "Home",

    # Automotive
    "autotrader.com": "Automotive", "cars.com": "Automotive",
    "kbb.com": "Automotive", "carfax.com": "Automotive",
    "edmunds.com": "Automotive", "cargurus.com": "Automotive",

    # Adult
    "pornhub.com": "Adult Content", "xvideos.com": "Adult Content",
    "xnxx.com": "Adult Content", "xhamster.com": "Adult Content",
    "redtube.com": "Adult Content", "onlyfans.com": "Adult Content",
    "chaturbate.com": "Adult Content", "spankbang.com": "Adult Content",
    "stripchat.com": "Adult Content", "livejasmin.com": "Adult Content",
    "bongacams.com": "Adult Content", "cam4.com": "Adult Content",
    "myfreecams.com": "Adult Content", "camsoda.com": "Adult Content",

    # Software
    "microsoft.com": "Technology", "mozilla.org": "Software",
    "opera.com": "Software", "brave.com": "Software",
    "adobe.com": "Software", "jetbrains.com": "Software Development",
    "atlassian.com": "Software Development",

    # Self-Hosting
    "nextcloud.com": "Self-Hosting", "synology.com": "Self-Hosting",
    "qnap.com": "Self-Hosting", "plex.tv": "Self-Hosting",

    # File Sharing
    "mega.nz": "File Sharing", "mediafire.com": "File Sharing",
    "wetransfer.com": "File Sharing", "1fichier.com": "File Sharing",
    "uploaded.net": "File Sharing",

    # URL Shorteners
    "bit.ly": "URL Shorteners", "tinyurl.com": "URL Shorteners",
    "t.co": "URL Shorteners", "goo.gl": "URL Shorteners",
    "ow.ly": "URL Shorteners", "is.gd": "URL Shorteners",

    # Link Aggregators
    "news.ycombinator.com": "Link Aggregators",
    "producthunt.com": "Link Aggregators",
    "lobste.rs": "Link Aggregators",
}

# TLD-based categorization hints for remaining domains
TLD_HINTS = {
    ".gov": "Government", ".gov.uk": "Government", ".gov.au": "Government",
    ".gov.in": "Government", ".gov.br": "Government", ".gov.cn": "Government",
    ".edu": "Education", ".ac.uk": "Education", ".edu.au": "Education",
    ".mil": "Government",
}


def categorize_by_tld(domain):
    for tld, cat in TLD_HINTS.items():
        if domain.endswith(tld):
            return cat
    return None


def should_skip(domain):
    dl = domain.lower()
    if dl in SKIP_DOMAINS:
        return True
    for skip in SKIP_DOMAINS:
        if dl.endswith("." + skip):
            return True
    # Skip very short domains (likely infra)
    if len(dl.replace(".", "")) < 4:
        return True
    # Skip domains that are clearly CDN/API subdomains
    for kw in ["cdn", "api", "static", "cache", "edge", "proxy", "lb-", "ns-",
               "mail.", "smtp.", "imap.", "pop.", "mx.", "dns.", "ns1.", "ns2.",
               "wpad.", "autodiscover.", "ftp."]:
        if kw in dl:
            return True
    return False


def main():
    zip_path = "C:/Users/--/.claude/projects/c--Users----repos/0fb6def4-6e02-4ff0-bcf2-4556792117bc/tool-results/webfetch-1780692342720-g5hvj1.zip"

    with zipfile.ZipFile(zip_path) as zf:
        with zf.open("top-1m.csv") as f:
            lines = f.read().decode("utf-8").strip().split("\n")

    tranco_domains = []
    for line in lines[:5000]:
        parts = line.split(",", 1)
        if len(parts) == 2:
            tranco_domains.append(parts[1].strip().lower())

    from bookmark_organizer_pro.core.default_categories import DEFAULT_CATEGORIES

    existing = set()
    for cat, pats in DEFAULT_CATEGORIES.items():
        for p in pats:
            if p.startswith("domain:"):
                existing.add(p[7:].lower().strip())

    additions = {}
    skipped_infra = 0
    skipped_existing = 0
    uncategorized = []

    for domain in tranco_domains:
        if should_skip(domain):
            skipped_infra += 1
            continue

        # Check if already in patterns
        parts = domain.split(".")
        found = False
        for i in range(len(parts)):
            if ".".join(parts[i:]) in existing:
                found = True
                break
        if found:
            skipped_existing += 1
            continue

        # Try known sites mapping
        cat = KNOWN_SITES.get(domain)
        if not cat:
            cat = categorize_by_tld(domain)

        if cat:
            additions.setdefault(cat, []).append(f"domain:{domain}")
        else:
            uncategorized.append(domain)

    total_added = sum(len(v) for v in additions.values())
    print("Tranco top 5000 analysis:")
    print(f"  Skipped (infrastructure): {skipped_infra}")
    print(f"  Already in patterns: {skipped_existing}")
    print(f"  Categorized: {total_added}")
    print(f"  Uncategorized (skipped): {len(uncategorized)}")

    # Now write to file
    filepath = "bookmark_organizer_pro/core/default_categories.py"
    with open(filepath, "r", encoding="utf-8") as f:
        file_lines = f.readlines()

    for cat, new_pats in sorted(additions.items()):
        if cat not in DEFAULT_CATEGORIES:
            print(f"  WARNING: category '{cat}' not in file")
            continue
        cat_header = f'    "{cat}"'
        in_cat = False
        insert_idx = None
        for i, line in enumerate(file_lines):
            if cat_header in line and ":" in line and "[" in line:
                in_cat = True
            elif in_cat and line.strip() == "],":
                insert_idx = i
                in_cat = False
                break

        if insert_idx is not None:
            deduped = [p for p in sorted(set(new_pats)) if p.lower() not in existing]
            if deduped:
                insert_lines = [f'        "{p}",\n' for p in deduped]
                file_lines = file_lines[:insert_idx] + insert_lines + file_lines[insert_idx:]
                # Track that these are now existing
                for p in deduped:
                    existing.add(p[7:].lower())
                print(f"  {cat}: +{len(deduped)}")

    with open(filepath, "w", encoding="utf-8") as f:
        f.writelines(file_lines)

    print(f"\nDone. Added {total_added} Tranco top-5000 domains.")
    if uncategorized:
        print("\nUncategorized domains (not added, first 50):")
        for d in uncategorized[:50]:
            print(f"  {d}")


if __name__ == "__main__":
    main()
