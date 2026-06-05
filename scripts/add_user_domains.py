#!/usr/bin/env python3
"""Add categorized domains from user's bookmark file to default_categories.py."""

import re
import sys
sys.path.insert(0, ".")

MANUAL_MAP = {
    # Forums / Imageboards
    "180chan.info": "Forums", "4chon.net": "Forums", "8chan.co": "Forums",
    "9chan.tw": "Forums", "alogs.space": "Forums", "anonib.al": "Forums",
    "kohlchan.net": "Forums", "masterchan.org": "Forums", "neinchan.com": "Forums",
    "16chan.xyz": "Forums", "kiwifarms.st": "Forums",
    "voat.co": "Forums", "saidit.net": "Forums", "ruqqus.com": "Forums",
    "communities.win": "Forums", "patriots.win": "Forums", "thedonald.win": "Forums",
    "ip2always.win": "Forums", "ip2.network": "Forums", "ip2.online": "Forums",
    "kbin.social": "Forums", "somethingawful.com": "Forums",
    "hackforums.net": "Forums", "nullforums.net": "Forums",
    "vbcity.com": "Forums", "godlikeproductions.com": "Forums",
    "snapzu.com": "Forums", "forum.mobilism.me": "Forums",
    "forum.wiziwig.eu": "Forums", "forum.userstyles.org": "Forums",
    "forums.mozillazine.org": "Forums", "forums.mvgroup.org": "Forums",
    "rooshvforum.com": "Forums", "psychforums.com": "Forums",
    "elevenforum.com": "Forums", "tenforums.com": "Forums",
    "w7forums.com": "Forums", "babiato.co": "Forums",
    "greentextarchive.net": "Forums",
    # News / Political
    "abcactionnews.com": "News", "anncoulter.com": "News",
    "americafirst.live": "News", "americanthinker.com": "News",
    "banned.video": "News", "censored.tv": "News",
    "daytoninformer.com": "News", "daytondailynews.com": "News",
    "dissenter.com": "News", "drudgereport.com": "News",
    "freespeech.tv": "News", "gab.com": "News", "gab.ai": "News",
    "infowars.com": "News", "mashable.com": "News",
    "mysuncoast.com": "News", "newsnow.com": "News",
    "newswars.com": "News", "parler.com": "News",
    "realclearpolitics.com": "News", "realclearpolling.com": "News",
    "revolver.news": "News", "seattlepi.com": "News",
    "tabletmag.com": "News", "thefederalist.com": "News",
    "tuckercarlson.com": "News", "truthsocial.com": "News",
    "wdtn.com": "News", "whio.com": "News", "whiotv.com": "News",
    "middletownjournal.com": "News", "wopular.com": "News",
    "fark.com": "News", "thenextweb.com": "News",
    "nysun.com": "News", "worldstar.com": "News",
    "worldstarhiphop.com": "News", "techtimes.com": "News",
    "c-span.org": "News",
    # Technology
    "alphr.com": "Technology", "androidpolice.com": "Technology",
    "addictivetips.com": "Technology", "bleepingcomputer.com": "Technology",
    "chromium.org": "Technology", "computerworld.com": "Technology",
    "computerhope.com": "Technology", "fudzilla.com": "Technology",
    "gottabemobile.com": "Technology", "gsmarena.com": "Technology",
    "infoworld.com": "Technology", "linustechtips.com": "Technology",
    "maketecheasier.com": "Technology", "neowin.net": "Technology",
    "osxdaily.com": "Technology", "windowscentral.com": "Technology",
    "xdaforums.com": "Technology", "appuals.com": "Technology",
    "sammobile.com": "Technology", "store.pine64.org": "Technology",
    "hardkernel.com": "Technology", "ladybird.org": "Technology",
    "pockethernet.com": "Technology",
    # System Administration
    "4sysops.com": "System Administration", "action1.com": "System Administration",
    "adaxes.com": "System Administration", "andrewstaylor.com": "System Administration",
    "autoelevate.com": "System Administration", "azuredevopslabs.com": "System Administration",
    "christitus.com": "System Administration", "connectwise.com": "System Administration",
    "dameware.com": "System Administration", "decentsecurity.com": "System Administration",
    "foxdeploy.com": "System Administration", "gfi.com": "System Administration",
    "goverlan.com": "System Administration", "intelliadmin.com": "System Administration",
    "itninja.com": "System Administration", "itprotoday.com": "System Administration",
    "knowbe4.com": "System Administration", "lazyadmin.nl": "System Administration",
    "lizardsystems.com": "System Administration", "majorgeeks.com": "System Administration",
    "mcpmag.com": "System Administration", "meshcommander.com": "System Administration",
    "msitpros.com": "System Administration", "ninjaone.com": "System Administration",
    "nliteos.com": "System Administration", "ntlite.com": "System Administration",
    "osdcloud.com": "System Administration", "ostechnix.com": "System Administration",
    "pdq.com": "System Administration", "petri.com": "System Administration",
    "powershellisfun.com": "System Administration",
    "practical365.com": "System Administration", "singularlabs.com": "System Administration",
    "solarwinds.com": "System Administration", "sophos.com": "System Administration",
    "splashtop.com": "System Administration", "superops.ai": "System Administration",
    "sysadmincasts.com": "System Administration",
    "sysadminpedia.com": "System Administration",
    "sysadmintoday.com": "System Administration",
    "systanddeploy.com": "System Administration",
    "thewindowsclub.com": "System Administration",
    "thirdtier.net": "System Administration", "threatlocker.com": "System Administration",
    "tweakhound.com": "System Administration", "windowsafg.com": "System Administration",
    "windowsitpro.com": "System Administration", "winhelponline.com": "System Administration",
    # Software Development
    "beautifier.io": "Software Development", "codepen.io": "Software Development",
    "devdocs.io": "Software Development", "expo.dev": "Software Development",
    "geeksforgeeks.org": "Software Development", "go.dev": "Software Development",
    "introjs.com": "Software Development", "jsfiddle.net": "Software Development",
    "reactbits.dev": "Software Development", "remotion.dev": "Software Development",
    "scrapy.org": "Software Development", "seleniumhq.org": "Software Development",
    "sourceforge.net": "Software Development", "lovable.dev": "Software Development",
    "supabase.com": "Software Development", "n8n.io": "Software Development",
    # Software (apps/tools)
    "adbappcontrol.com": "Software", "autohotkey.com": "Software",
    "autoitscript.com": "Software", "chocolatey.org": "Software",
    "custopack.com": "Software", "dbpoweramp.com": "Software",
    "displayfusion.com": "Software", "ezgif.com": "Software",
    "fcportables.com": "Software", "filehippo.com": "Software",
    "freewaregenius.com": "Software", "freetubeapp.io": "Software",
    "grayjay.app": "Software", "imagemagick.org": "Software",
    "jdownloader.org": "Software", "librewolf.net": "Software",
    "macrium.com": "Software", "marticliment.com": "Software",
    "ninite.com": "Software", "nchsoftware.com": "Software",
    "partitionwizard.com": "Software", "pcdecrapifier.com": "Software",
    "portableapps.com": "Software", "portapps.io": "Software",
    "sordum.org": "Software", "spicetify.app": "Software",
    "tinypng.com": "Software", "uninstalr.com": "Software",
    "voidtools.com": "Software", "wincustomize.com": "Software",
    "winstall.app": "Software", "userstyles.world": "Software",
    "greasyfork.org": "Software", "stylebot.me": "Software",
    "zamzar.com": "Software", "magiceraser.org": "Software",
    "kapwing.com": "Software", "watermarkremover.io": "Software",
    "ultimatevocalremover.com": "Software", "videodownloadtool.io": "Software",
    # Artificial Intelligence
    "chat.deepseek.com": "Artificial Intelligence",
    "chat.qwen.ai": "Artificial Intelligence",
    "civitai.com": "Artificial Intelligence",
    "cursor.com": "Artificial Intelligence",
    "elevenlabs.io": "Artificial Intelligence",
    "geminivideo.studio": "Artificial Intelligence",
    "goblin.tools": "Artificial Intelligence",
    "grok.com": "Artificial Intelligence",
    "hailuo-02.com": "Artificial Intelligence",
    "hailuoai.video": "Artificial Intelligence",
    "heygen.com": "Artificial Intelligence",
    "kaiber.ai": "Artificial Intelligence",
    "lenso.ai": "Artificial Intelligence",
    "lifearchitect.ai": "Artificial Intelligence",
    "livebench.ai": "Artificial Intelligence",
    "murf.ai": "Artificial Intelligence",
    "napkin.ai": "Artificial Intelligence",
    "nightcafe.studio": "Artificial Intelligence",
    "openrouter.ai": "Artificial Intelligence",
    "otter.ai": "Artificial Intelligence",
    "pi.ai": "Artificial Intelligence",
    "pixverse.ai": "Artificial Intelligence",
    "runwayml.com": "Artificial Intelligence",
    "sora.com": "Artificial Intelligence",
    "suno.com": "Artificial Intelligence",
    "vivalabs.ai": "Artificial Intelligence",
    "beautiful.ai": "Artificial Intelligence",
    # Cloud Computing
    "contabo.com": "Cloud Computing", "cloudconvert.com": "Cloud Computing",
    "cloudacademy.com": "Cloud Computing", "netlify.com": "Cloud Computing",
    "tailscale.com": "Cloud Computing",
    # Cybersecurity
    "amiunique.org": "Cybersecurity", "d3ward.github.io": "Cybersecurity",
    "dnscheck.tools": "Cybersecurity", "dnsviz.net": "Cybersecurity",
    "firebog.net": "Cybersecurity", "filterlists.com": "Cybersecurity",
    "grapheneos.org": "Cybersecurity", "ipleak.net": "Cybersecurity",
    "isc.sans.edu": "Cybersecurity", "joesandbox.com": "Cybersecurity",
    "privacy.com": "Cybersecurity", "privacy.sexy": "Cybersecurity",
    "privacytests.org": "Cybersecurity", "safing.io": "Cybersecurity",
    "simplelogin.io": "Cybersecurity", "temp-mail.org": "Cybersecurity",
    "viz.greynoise.io": "Cybersecurity", "astrill.com": "Cybersecurity",
    "darknetdiaries.com": "Cybersecurity", "ericzimmerman.github.io": "Cybersecurity",
    # Entertainment / Streaming
    "123moviestogo.com": "Entertainment", "arc018.to": "Entertainment",
    "bflix.la": "Entertainment", "cine.su": "Entertainment",
    "cinevids.site": "Entertainment", "couchtuner.show": "Entertainment",
    "daddylive.mp": "Entertainment", "fmovies.solar": "Entertainment",
    "flixmomo.com": "Entertainment", "gomovies.sc": "Entertainment",
    "gomovies4k.site": "Entertainment", "hdonline.is": "Entertainment",
    "lookmovie2.to": "Entertainment", "m4uhd.page": "Entertainment",
    "movie-web.app": "Entertainment", "muctau.com": "Entertainment",
    "myflixertv.to": "Entertainment", "nfl123.com": "Entertainment",
    "nyafilm13.com": "Entertainment", "popcornfilmz.com": "Entertainment",
    "projectfree.tv": "Entertainment", "putlocker.is": "Entertainment",
    "showbox.works": "Entertainment", "solarmoviez.ru": "Entertainment",
    "thetvapp.to": "Entertainment", "thetvdb.com": "Entertainment",
    "uflix.to": "Entertainment", "ufreetv.com": "Entertainment",
    "ustv247.tv": "Entertainment", "w-123movies.com": "Entertainment",
    "watchluna.com": "Entertainment", "watchnewslive.tv": "Entertainment",
    "streamxtv.tech": "Entertainment", "gosolo.tv": "Entertainment",
    "publiciptv.com": "Entertainment", "usnewslive.tv": "Entertainment",
    "imdb.com": "Entertainment", "justwatch.com": "Entertainment",
    "siriusxm.com": "Entertainment", "pandora.com": "Entertainment",
    "xkcd.com": "Entertainment", "goodreads.com": "Entertainment",
    "ted.com": "Entertainment", "soundcloud.com": "Entertainment",
    "bandcamp.com": "Entertainment",
    # Video
    "bitwave.tv": "Video", "cozy.tv": "Video",
    "dailymotion.com": "Video", "dlive.tv": "Video",
    "kick.com": "Video", "liveomg.com": "Video",
    "odysee.com": "Video", "rumble.com": "Video",
    "streamable.com": "Video", "streamlabs.com": "Video",
    "trovo.live": "Video", "yewtu.be": "Video",
    "bitchute.com": "Video", "restream.io": "Video",
    # Social Media
    "bio.link": "Social Media", "mewe.com": "Social Media",
    "minds.com": "Social Media", "poa.st": "Social Media",
    "subscribestar.com": "Social Media", "tango.me": "Social Media",
    "patreon.com": "Social Media", "gofundme.com": "Social Media",
    "nitter.net": "Social Media", "twstalker.com": "Social Media",
    # File Sharing / Torrents
    "annas-archive.li": "File Sharing", "annas-archive.org": "File Sharing",
    "bitsearch.to": "File Sharing", "documentarytorrents.com": "File Sharing",
    "eztvx.to": "File Sharing", "houseoftorrents.me": "File Sharing",
    "idope.se": "File Sharing", "kickass.so": "File Sharing",
    "kickasstorrent.cr": "File Sharing", "kickasstorrents.to": "File Sharing",
    "libgen.is": "File Sharing", "limetorrents.cc": "File Sharing",
    "magnetdl.com": "File Sharing", "opentrackers.org": "File Sharing",
    "pirates-forum.org": "File Sharing", "rarbg.to": "File Sharing",
    "rutracker.org": "File Sharing", "seedboxes.cc": "File Sharing",
    "thepiratebay.org": "File Sharing", "thepiratebay.asia": "File Sharing",
    "torrentgalaxy.to": "File Sharing", "torrentinvites.org": "File Sharing",
    "torrentleech.org": "File Sharing", "ultraseedbox.com": "File Sharing",
    "whatbox.ca": "File Sharing", "yify-torrent.org": "File Sharing",
    "yify-torrents.com": "File Sharing", "yts.ag": "File Sharing",
    "zooqle.com": "File Sharing", "filenext.com": "File Sharing",
    "filecr.com": "File Sharing", "topfiles.org": "File Sharing",
    "godownloads.net": "File Sharing", "godownloads.org": "File Sharing",
    "massgrave.dev": "File Sharing",
    # Adult Content
    "16ebalka.ru.actor": "Adult Content", "av4us.online": "Adult Content",
    "camfuze.com": "Adult Content", "erotom.com": "Adult Content",
    "filtradas.com": "Adult Content", "ins-dream.com": "Adult Content",
    "jerkersworld.com": "Adult Content", "literotica.com": "Adult Content",
    "luxuretv.com": "Adult Content", "noodlemagazine.com": "Adult Content",
    "tabootube.xxx": "Adult Content", "tblop.com": "Adult Content",
    "thisvid.com": "Adult Content", "usluts.com": "Adult Content",
    # Design / Graphics
    "aedownload.com": "Design", "aegraphic.com": "Design",
    "aescripts.com": "Design", "aeriver.com": "Design",
    "avaxgfx.com": "Design", "awesomeflyer.com": "Design",
    "brandcrowd.com": "Design", "diybookcovers.com": "Design",
    "elegantflyer.com": "Design", "gfxdownload.com": "Design",
    "gfxdownload.net": "Design", "gfxdrug.com": "Design",
    "gfxpeers.net": "Design", "graphicriver.net": "Design",
    "graphixtree.com": "Design", "hunterae.com": "Design",
    "iconarchive.com": "Design", "intro-hd.net": "Design",
    "lookae.com": "Design", "mockplus.com": "Design",
    "nitrogfx.pro": "Design", "psdflyer.co": "Design",
    "psdly.com": "Design", "psdly.io": "Design",
    "searchgfx.com": "Design", "styleflyers.com": "Design",
    "vfxdownload.net": "Design", "vfxdownloads.net": "Design",
    # Media Production
    "audiojungle.net": "Media Production", "artlist.io": "Media Production",
    "bensound.com": "Media Production", "bigfilms.shop": "Media Production",
    "cuttersweekly.com": "Media Production", "dacast.com": "Media Production",
    "freevideoeffect.com": "Media Production", "storyblocks.com": "Media Production",
    "telestream.net": "Media Production", "videohive.net": "Media Production",
    "videohelp.com": "Media Production",
    # Finance
    "bitcoinwisdom.com": "Finance", "bitbo.io": "Finance",
    "coindesk.com": "Finance", "creditonebank.com": "Finance",
    "finviz.com": "Finance", "hedgefollow.com": "Finance",
    "macrotrends.net": "Finance", "nationwide.com": "Finance",
    "predictit.org": "Finance", "thehartford.com": "Finance",
    # Careers
    "careerbuilder.com": "Careers", "careercup.com": "Careers",
    "careervault.io": "Careers", "elance.com": "Careers",
    "governmentjobs.com": "Careers", "hloom.com": "Careers",
    "kellyservices.com": "Careers", "linkup.com": "Careers",
    "open-resume.com": "Careers", "remoteleaf.com": "Careers",
    "roberthalf.com": "Careers", "simplyhired.com": "Careers",
    "snagajob.com": "Careers", "thumbtack.com": "Careers",
    "unwoke.hr": "Careers", "weworkremotely.com": "Careers",
    # Shopping
    "americanfreight.com": "Shopping", "bonanza.com": "Shopping",
    "costco.com": "Shopping", "cyberpowerpc.com": "Shopping",
    "ibuypower.com": "Shopping", "keepa.com": "Shopping",
    "monoprice.com": "Shopping", "nowinstock.net": "Shopping",
    "secretlab.co": "Shopping", "slickdeals.net": "Shopping",
    "stockinformer.com": "Shopping", "swappa.com": "Shopping",
    "thinkgeek.com": "Shopping", "temu.com": "Shopping",
    "ar15.com": "Shopping", "ar500armor.com": "Shopping",
    "armsunlimited.com": "Shopping", "basspro.com": "Shopping",
    "budsgunshop.com": "Shopping", "cabelas.com": "Shopping",
    "galcogunleather.com": "Shopping", "grabagun.com": "Shopping",
    "gunbroker.com": "Shopping", "guns.com": "Shopping",
    "gunprime.com": "Shopping", "impactguns.com": "Shopping",
    "springfield-armory.com": "Shopping", "truegunvalue.com": "Shopping",
    "sportsmansguide.com": "Shopping",
    # Health
    "23andme.com": "Health", "alivenhealthy.com": "Health",
    "allthingsgym.com": "Health", "askapatient.com": "Health",
    "athleanx.com": "Health", "cernerhealth.com": "Health",
    "gnc.com": "Health", "hims.com": "Health",
    "lafitness.com": "Health", "lifeextension.com": "Health",
    "liftmode.com": "Health", "nootropicsdepot.com": "Health",
    "weights.com": "Health",
    # Weather
    "darksitefinder.com": "Weather", "earth.nullschool.net": "Weather",
    "farmersalmanac.com": "Weather", "iweathernet.com": "Weather",
    "meteoblue.com": "Weather", "spaghettimodels.com": "Weather",
    "tropicaltidbits.com": "Weather", "wxnation.com": "Weather",
    "worldmonitor.app": "Weather", "zoom.earth": "Weather",
    # Government
    "flhsmv.gov": "Government", "ic3.gov": "Government",
    "ohio.gov": "Government", "tax.ohio.gov": "Government",
    "congress.gov": "Government",
    # Education
    "certcollection.net": "Education", "certcollection.org": "Education",
    "exam-hub.com": "Education", "examcollection.com": "Education",
    "exam-labs.com": "Education", "examtopics.com": "Education",
    "freeallcourse.com": "Education", "isc2.org": "Education",
    "lpi.org": "Education", "professormesser.com": "Education",
    "qwiklabs.com": "Education", "tutsnode.org": "Education",
    # Reference
    "alternativeto.net": "Reference", "answerthepublic.com": "Reference",
    "convertcase.net": "Reference", "everytimezone.com": "Reference",
    "fsymbols.com": "Reference", "hemingwayapp.com": "Reference",
    "lingojam.com": "Reference", "tineye.com": "Reference",
    "indexmundi.com": "Reference",
    # Productivity
    "diagrams.net": "Productivity", "honeybook.com": "Productivity",
    "jotform.com": "Productivity", "johnnydecimal.com": "Productivity",
    "pdfescape.com": "Productivity", "pdffiller.com": "Productivity",
    "signwell.com": "Productivity", "start.me": "Productivity",
    # Travel
    "allegiantair.com": "Travel", "hotwire.com": "Travel",
    "skyscanner.net": "Travel", "usevacay.com": "Travel",
    "wanderu.com": "Travel",
    # Real Estate
    "estately.com": "Real Estate", "rentcafe.com": "Real Estate",
    # Gaming
    "digminecraft.com": "Gaming", "geysermc.org": "Gaming",
    "minecraft-mp.com": "Gaming", "mcprohosting.com": "Gaming",
    "papermc.io": "Gaming", "supremacy1914.com": "Gaming",
    # Self-Hosting
    "rustdesk.com": "Self-Hosting", "osticket.com": "Self-Hosting",
    # Internal Networks
    "74.113.106.162": "Internal Networks",
    # Link Aggregators
    "fmhy.net": "Link Aggregators", "fmhy.pages.dev": "Link Aggregators",
    # URL Shorteners
    "7kt.se": "URL Shorteners", "ez.lol": "URL Shorteners",
    "sptfy.in": "URL Shorteners",
    # Photography
    "photobucket.com": "Photography", "pngwing.com": "Photography",
    "copyseeker.net": "Photography", "iloveimg.com": "Photography",
    # Business
    "businessinsider.com": "Business", "flippa.com": "Business",
    "legalzoom.com": "Business", "bbb.org": "Business",
    # Automotive
    "f150online.com": "Automotive",
    # Home
    "cabinetdoors.com": "Home", "lumberliquidators.com": "Home",
    "roomarranger.com": "Home",
    # Food
    "cheryls.com": "Food", "chocolate.com": "Food",
    # Science
    "nuclearsecrecy.com": "Science",
}


def main():
    from bookmark_organizer_pro.core.default_categories import DEFAULT_CATEGORIES

    existing = set()
    for cat, pats in DEFAULT_CATEGORIES.items():
        for p in pats:
            existing.add(p.strip().lower())

    additions = {}
    skipped = 0
    for domain, category in MANUAL_MAP.items():
        pattern = f"domain:{domain}"
        if pattern.lower() in existing:
            skipped += 1
            continue
        if category not in DEFAULT_CATEGORIES:
            print(f"WARNING: category '{category}' not found")
            continue
        additions.setdefault(category, []).append(pattern)

    total = sum(len(v) for v in additions.values())
    print(f"Adding {total} new patterns ({skipped} already exist)")

    filepath = "bookmark_organizer_pro/core/default_categories.py"
    with open(filepath, "r", encoding="utf-8") as f:
        lines = f.readlines()

    # Find each category and insert before its closing ]
    for cat, new_pats in sorted(additions.items()):
        cat_header = f'    "{cat}"'
        in_cat = False
        insert_idx = None
        for i, line in enumerate(lines):
            if cat_header in line and ":" in line and "[" in line:
                in_cat = True
            elif in_cat and line.strip() == "],":
                insert_idx = i
                in_cat = False
                break

        if insert_idx is not None:
            insert_lines = [f'        "{p}",\n' for p in sorted(new_pats)]
            lines = lines[:insert_idx] + insert_lines + lines[insert_idx:]
            print(f"  {cat}: +{len(new_pats)}")
        else:
            print(f"  WARNING: could not find '{cat}' closing bracket")

    with open(filepath, "w", encoding="utf-8") as f:
        f.writelines(lines)

    print(f"\nWrote {total} new patterns to {filepath}")


if __name__ == "__main__":
    main()
