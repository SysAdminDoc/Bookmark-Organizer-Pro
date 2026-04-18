"""Default categorization patterns - 892 patterns across 32 categories.

Built from real-world bookmark analysis of 5,000+ bookmarks. Covers 500+ popular
domains. Pattern types supported: plain, domain:, keyword:, regex:, path:, title:.
"""

DEFAULT_CATEGORIES = {
    "Uncategorized / Needs Review": [
        "example.com", "example.org", "test.", "demo.", "staging."
    ],
    "Adult & Mature Content": [
        "pornhub.com", "xvideos.com", "xnxx.com", "xhamster.com", "redtube.com",
        "porn.", "xxx.", "chaturbate.com", "onlyfans.com", "fansly.com",
        "youporn.com", "tube8.com", "spankbang.com", "eporner.com",
        "motherless.com", "youjizz.com", "fuq.com", "nudevista.com",
        "keyword:porn", "keyword:xxx", "keyword:nsfw", "keyword:erotic"
    ],
    "Redirects, Trackers & Shorteners": [
        "domain:bit.ly", "domain:bitly.com", "domain:tinyurl.com",
        "domain:t.co", "domain:goo.gl", "domain:ow.ly",
        "domain:linktr.ee", "domain:linkin.bio",
        "domain:rebrand.ly", "domain:cutt.ly", "domain:is.gd",
        "domain:v.gd", "domain:shorturl.at",
        "domain:linkvertise.com", "domain:adf.ly", "domain:ouo.io",
        "redirect.", "tracking.", "click.",
        "utm_source=", "fbclid=", "gclid=", "mc_eid="
    ],
    "Internal Tools & Dashboards": [
        "localhost", "127.0.0.1", "192.168.", "10.0.", "172.16.", ".local",
        ".internal", ".lan", ":3000", ":8080", ":8443", ":9090", ":5000",
        "/admin", "/dashboard", "admin.", "dashboard.", "internal.", "intranet.",
        "domain:pfsense", "domain:opnsense", "domain:unifi"
    ],
    "Privacy & Security": [
        "domain:1password.com", "domain:lastpass.com", "domain:bitwarden.com",
        "domain:protonmail.com", "domain:proton.me", "domain:nordvpn.com",
        "domain:expressvpn.com", "domain:mullvad.net", "domain:torproject.org",
        "domain:signal.org", "domain:haveibeenpwned.com", "domain:privacyguides.org",
        "domain:privacytools.io", "domain:virustotal.com", "domain:keepassxc.org",
        "domain:tails.boum.org", "domain:whonix.org",
        "keyword:vpn", "keyword:privacy", "keyword:encrypt"
    ],
    "Self-Hosted & Homelab": [
        "domain:pfsense.org", "domain:opnsense.org", "domain:proxmox.com",
        "domain:truenas.com", "domain:unraid.net", "domain:synology.com",
        "domain:home-assistant.io", "domain:jellyfin.org", "domain:plex.tv",
        "domain:sonarr.tv", "domain:radarr.video", "domain:nextcloud.com",
        "domain:pi-hole.net", "domain:portainer.io", "domain:emby.media",
        "domain:cockpit-project.org", "domain:homer-dashboard.com",
        "domain:wireguard.com", "domain:tailscale.com", "domain:zerotier.com"
    ],
    "SysAdmin & IT": [
        # Windows & Group Policy
        "domain:getadmx.com", "domain:admx.help", "domain:schneegans.de",
        "domain:winaero.com", "keyword:group policy", "keyword:gpedit",
        "keyword:admx", "keyword:unattend", "keyword:windows 10", "keyword:windows 11",
        "keyword:windows server", "keyword:powershell", "keyword:registry",
        "keyword:sccm", "keyword:intune", "keyword:wsus",
        "domain:go.microsoft.com", "domain:learn.microsoft.com",
        "domain:docs.microsoft.com", "domain:devblogs.microsoft.com",
        # Networking & DNS
        "domain:dnscheck.tools", "domain:mxtoolbox.com", "domain:whatismyip.com",
        "domain:dnschecker.org", "domain:dnsviz.net", "domain:ipchicken.com",
        "domain:whatsmydns.net", "domain:who.is", "domain:whois.com",
        "domain:speedtest.net", "domain:speakeasy.net", "domain:wifiman.com",
        "keyword:speed test", "keyword:dns", "keyword:whois",
        # Hardware & Drivers
        "domain:dell.com", "domain:hp.com", "domain:lenovo.com",
        "domain:intel.com", "domain:amd.com", "domain:nvidia.com",
        "domain:toshiba.com", "domain:gsmarena.com", "domain:amcrest.com",
        "domain:tomshardware.com", "domain:anandtech.com", "domain:pcpartpicker.com",
        # IT Forums & Resources
        "domain:tenforums.com", "domain:elevenforum.com", "domain:serverfault.com",
        "domain:spiceworks.com", "domain:ghacks.net", "domain:askwoody.com",
        "domain:howtogeek.com", "domain:techrepublic.com",
        "domain:windowscentral.com", "domain:neowin.net", "domain:theregister.com",
        "domain:computerworld.com", "domain:bleepingcomputer.com",
        # Remote Access & Management
        "domain:splashtop.com", "domain:screenconnect.com", "domain:connectwise.com",
        "domain:ninjaone.com", "domain:pdq.com", "domain:teamviewer.com",
        "domain:anydesk.com",
        "keyword:managed it", "keyword:it services", "keyword:it support",
        "keyword:endpoint", "keyword:patch management", "keyword:rmm"
    ],
    "Development & Programming": [
        # Code Hosting
        "domain:github.com", "domain:gitlab.com", "domain:bitbucket.org",
        "domain:codeberg.org", "domain:sourceforge.net",
        "domain:gist.github.com", "domain:raw.githubusercontent.com",
        # Q&A & Community
        "domain:stackoverflow.com", "domain:stackexchange.com",
        "domain:superuser.com", "domain:serverfault.com", "domain:dev.to",
        # IDEs & Playgrounds
        "domain:codepen.io", "domain:jsfiddle.net", "domain:replit.com",
        "domain:codesandbox.io", "domain:stackblitz.com",
        # Package Managers
        "domain:npmjs.com", "domain:pypi.org", "domain:crates.io",
        "domain:packagist.org", "domain:rubygems.org", "domain:nuget.org",
        # Competitive
        "domain:hackerrank.com", "domain:leetcode.com", "domain:codeforces.com",
        # Documentation
        "domain:developer.mozilla.org", "domain:w3schools.com",
        "domain:css-tricks.com", "domain:smashingmagazine.com",
        # Userscripts & Extensions
        "domain:greasyfork.org", "domain:openuserjs.org",
        "domain:userstyles.world", "domain:userstyles.org", "domain:userscripts.org",
        "domain:chromewebstore.google.com", "domain:addons.mozilla.org",
        "domain:uso.kkx.one",
        # Web Development
        "domain:themeforest.net", "domain:tailwindcss.com",
        "domain:vercel.com", "domain:netlify.com", "domain:heroku.com",
        # Dev Tools
        "domain:regex101.com", "domain:jsonformatter.org",
        "domain:producthunt.com", "domain:pastebin.com",
        "domain:community.chocolatey.org", "domain:chocolatey.org",
        "domain:winget.run", "domain:xda-developers.com",
        "domain:play.google.com",
        "keyword:userscript", "keyword:tampermonkey", "keyword:greasemonkey"
    ],
    "AI & Machine Learning": [
        # AI Assistants
        "domain:openai.com", "domain:anthropic.com", "domain:claude.ai",
        "domain:status.claude.com", "domain:chatgpt.com", "domain:chat.openai.com",
        "domain:gemini.google.com", "domain:aistudio.google.com", "domain:labs.google",
        "domain:poe.com", "domain:perplexity.ai", "domain:deepseek.com",
        "domain:chat.deepseek.com", "domain:copilot.microsoft.com",
        "domain:pi.ai", "domain:character.ai", "domain:chub.ai",
        "domain:chat.qwen.ai",
        # AI Development
        "domain:huggingface.co", "domain:kaggle.com",
        "domain:tensorflow.org", "domain:pytorch.org",
        "domain:colab.research.google.com", "domain:replicate.com",
        "domain:ollama.com", "domain:lmstudio.ai", "domain:cursor.com",
        "domain:cursor.sh", "domain:codeium.com", "domain:together.ai",
        "domain:groq.com", "domain:cohere.com", "domain:mistral.ai",
        "domain:ai.google.dev", "domain:console.anthropic.com",
        "domain:docs.anthropic.com", "domain:n8n.io",
        # AI Art & Media
        "domain:midjourney.com", "domain:stability.ai", "domain:civitai.com",
        "domain:suno.com", "domain:suno.ai", "domain:udio.com",
        "domain:elevenlabs.io", "domain:runwayml.com", "domain:kaiber.ai",
        "domain:leonardo.ai", "domain:ideogram.ai", "domain:pika.art",
        "domain:luma.ai", "domain:dreamstudio.ai", "domain:clipdrop.co",
        "domain:nightcafe.studio", "domain:heygen.com", "domain:murf.ai",
        "domain:hailuoai.video", "domain:napkin.ai",
        "keyword:ai model", "keyword:llm", "keyword:large language",
        "keyword:machine learning", "keyword:deep learning"
    ],
    "Cloud & Infrastructure": [
        "domain:aws.amazon.com", "domain:console.aws.amazon.com",
        "domain:azure.microsoft.com", "domain:portal.azure.com",
        "domain:cloud.google.com", "domain:digitalocean.com",
        "domain:linode.com", "domain:vultr.com", "domain:hetzner.com",
        "domain:cloudflare.com", "domain:dash.cloudflare.com",
        "domain:namecheap.com", "domain:godaddy.com", "domain:domains.google.com",
        "domain:squarespace.com", "domain:wordpress.com", "domain:wordpress.org",
        "domain:cpanel.com", "domain:one.com", "domain:siteground.com",
        "domain:hostinger.com", "domain:bluehost.com", "domain:dreamhost.com",
        "keyword:docker", "keyword:kubernetes", "keyword:terraform",
        "keyword:ansible", "keyword:vmware", "keyword:esxi", "keyword:proxmox"
    ],
    "News & Media": [
        "domain:cnn.com", "domain:bbc.com", "domain:bbc.co.uk",
        "domain:reuters.com", "domain:apnews.com", "domain:nytimes.com",
        "domain:washingtonpost.com", "domain:theguardian.com",
        "domain:bloomberg.com", "domain:techcrunch.com",
        "domain:foxnews.com", "domain:nbcnews.com", "domain:cbsnews.com",
        "domain:abcnews.go.com", "domain:npr.org", "domain:usatoday.com",
        "domain:latimes.com", "domain:nypost.com", "domain:msn.com",
        "domain:news.google.com", "domain:news.ycombinator.com",
        "domain:breitbart.com", "domain:dailymail.co.uk", "domain:zerohedge.com",
        "domain:infowars.com", "domain:newsmax.com", "domain:theblaze.com",
        "domain:drudgereport.com", "domain:revolver.news",
        "domain:thegatewaypundit.com", "domain:americanthinker.com",
        "domain:theverge.com", "domain:wired.com", "domain:engadget.com",
        "domain:vice.com", "domain:vox.com", "domain:slate.com",
        "domain:salon.com", "domain:huffpost.com", "domain:politico.com",
        "domain:thehill.com", "domain:axios.com", "domain:mashable.com",
        "domain:thedailybeast.com", "domain:medium.com", "domain:substack.com",
        "domain:libertylinks.io"
    ],
    "Weather & Meteorology": [
        "domain:weather.com", "domain:weather.gov", "domain:noaa.gov",
        "domain:nhc.noaa.gov", "domain:star.nesdis.noaa.gov",
        "domain:tropicaltidbits.com", "domain:wunderground.com",
        "domain:accuweather.com", "domain:windy.com", "domain:ventusky.com",
        "domain:earth.nullschool.net", "domain:zoom.earth",
        "domain:lightningmaps.org", "domain:spaghettimodels.com",
        "keyword:weather", "keyword:forecast", "keyword:hurricane",
        "keyword:tropical storm", "keyword:tornado", "keyword:radar",
        "keyword:doppler", "keyword:severe weather"
    ],
    "Social Media": [
        "domain:twitter.com", "domain:x.com", "domain:nitter.net",
        "domain:facebook.com", "domain:m.facebook.com", "domain:fb.com",
        "domain:instagram.com", "domain:linkedin.com",
        "domain:tiktok.com", "domain:pinterest.com", "domain:tumblr.com",
        "domain:snapchat.com", "domain:threads.net",
        "domain:bluesky.app", "domain:bsky.app",
        "domain:mastodon.social", "domain:nextdoor.com"
    ],
    "Forums & Communities": [
        "domain:reddit.com", "domain:old.reddit.com", "domain:new.reddit.com",
        "domain:quora.com", "domain:discord.com", "domain:discord.gg",
        "domain:slack.com", "domain:telegram.org", "domain:t.me",
        "domain:boards.4chan.org", "domain:boards.4channel.org",
        "domain:4chan.org", "domain:4channel.org",
        "domain:godlikeproductions.com",
        "domain:forums.somethingawful.com", "domain:somethingawful.com",
        "domain:kiwifarms.net", "domain:imgur.com",
        "domain:voat.co", "domain:scored.co", "domain:communities.win",
        "domain:gab.com", "domain:truthsocial.com", "domain:minds.com",
        "domain:parler.com", "domain:gettr.com", "domain:ruqqus.com",
        "domain:8ch.net", "domain:8kun.top"
    ],
    "Shopping & E-commerce": [
        "domain:amazon.com", "domain:smile.amazon.com", "domain:camelcamelcamel.com",
        "domain:ebay.com", "domain:walmart.com", "domain:target.com",
        "domain:bestbuy.com", "domain:etsy.com", "domain:aliexpress.com",
        "domain:shopify.com", "domain:newegg.com", "domain:bhphotovideo.com",
        "domain:wish.com", "domain:temu.com", "domain:shein.com",
        "domain:wayfair.com", "domain:homedepot.com", "domain:lowes.com",
        "domain:costco.com", "domain:samsclub.com", "domain:ikea.com",
        "domain:overstock.com", "domain:menards.com", "domain:harborfreight.com",
        "domain:monoprice.com", "domain:kohls.com", "domain:macys.com",
        "domain:nordstrom.com", "domain:zappos.com",
        "domain:craigslist.org", "domain:offerup.com", "domain:mercari.com",
        "domain:poshmark.com", "domain:swappa.com",
        "domain:fedex.com", "domain:ups.com", "domain:usps.com",
        "domain:cvs.com", "domain:walgreens.com",
        # Firearms & Outdoor
        "domain:gunbroker.com", "domain:guns.com", "domain:impactguns.com",
        "domain:palmettostatearmory.com", "domain:budsgunshop.com",
        "domain:classicfirearms.com", "domain:ammoseek.com",
        "domain:midwayusa.com", "domain:brownells.com",
        "domain:cheaperthandirt.com", "domain:sportsmansguide.com",
        "keyword:firearm", "keyword:ammo", "keyword:holster"
    ],
    "Entertainment & Streaming": [
        # Video Streaming
        "domain:youtube.com", "domain:youtu.be", "domain:music.youtube.com",
        "domain:netflix.com", "domain:hulu.com", "domain:disneyplus.com",
        "domain:hbomax.com", "domain:max.com", "domain:primevideo.com",
        "domain:peacocktv.com", "domain:paramountplus.com",
        "domain:pluto.tv", "domain:tubi.tv", "domain:crackle.com",
        "domain:vudu.com", "domain:dailymotion.com", "domain:vimeo.com",
        # Live Streaming
        "domain:twitch.tv", "domain:kick.com", "domain:rumble.com",
        "domain:fishtank.live", "domain:dlive.tv", "domain:trovo.live",
        "domain:bitwave.tv", "domain:censored.tv", "domain:cozy.tv",
        "domain:bitchute.com", "domain:odysee.com", "domain:liveomg.com",
        "domain:putchannel.com", "domain:patreon.com",
        # Movies & TV
        "domain:imdb.com", "domain:rottentomatoes.com", "domain:letterboxd.com",
        "domain:justwatch.com", "domain:thetvdb.com", "domain:themoviedb.org",
        "domain:trakt.tv", "domain:abetterqueue.com",
        "domain:arc018.to", "domain:flixmomo.com",
        # Music & Audio
        "domain:spotify.com", "domain:open.spotify.com",
        "domain:soundcloud.com", "domain:bandcamp.com",
        "domain:last.fm", "domain:deezer.com", "domain:tidal.com",
        "domain:music.apple.com", "domain:distrokid.com",
        "domain:tothebestof.com", "domain:genius.com",
        "domain:tunetidy.com", "domain:cduniverse.com",
        "domain:crunchyroll.com",
        "keyword:asmr"
    ],
    "Gaming": [
        "domain:steam.com", "domain:steampowered.com", "domain:store.steampowered.com",
        "domain:epicgames.com", "domain:gog.com", "domain:itch.io",
        "domain:xbox.com", "domain:playstation.com", "domain:nintendo.com",
        "domain:ign.com", "domain:gamespot.com", "domain:pcgamer.com",
        "domain:kotaku.com", "domain:polygon.com",
        "domain:curseforge.com", "domain:modrinth.com", "domain:minecraft.net",
        "domain:mcprohosting.com", "domain:dev.bukkit.org",
        "domain:roblox.com", "domain:ea.com", "domain:ubisoft.com"
    ],
    "Finance & Banking": [
        "domain:chase.com", "domain:bankofamerica.com", "domain:wellsfargo.com",
        "domain:paypal.com", "domain:venmo.com", "domain:robinhood.com",
        "domain:fidelity.com", "domain:coinbase.com", "domain:mint.com",
        "domain:creditkarma.com", "domain:turbotax.com",
        "domain:irs.gov", "domain:stripe.com", "domain:square.com",
        "domain:quickbooks.intuit.com", "domain:freshbooks.com",
        "domain:gusto.com", "domain:paylocity.com",
        "keyword:credit union", "keyword:banking"
    ],
    "Education & Learning": [
        "domain:coursera.org", "domain:udemy.com", "domain:edx.org",
        "domain:khanacademy.org", "domain:udacity.com", "domain:codecademy.com",
        "domain:freecodecamp.org", "domain:duolingo.com", "domain:masterclass.com",
        "domain:pluralsight.com", "domain:skillshare.com", "domain:lynda.com",
        "domain:flatiron.com",
        "keyword:certification", "keyword:practice test",
        "keyword:comptia", "keyword:microsoft cert"
    ],
    "Reference & Research": [
        "domain:wikipedia.org", "domain:en.wikipedia.org", "domain:britannica.com",
        "domain:merriam-webster.com", "domain:dictionary.com",
        "domain:scholar.google.com", "domain:arxiv.org", "domain:pubmed.gov",
        "domain:wolframalpha.com", "domain:archive.org", "domain:web.archive.org",
        "domain:biblegateway.com", "domain:quora.com",
        # Flight & Ship Tracking
        "domain:globe.airplanes.live", "domain:globe.adsbexchange.com",
        "domain:flightradar24.com", "domain:flightaware.com",
        "domain:planefinder.net", "domain:marinetraffic.com",
        "domain:vesselfinder.com",
        # Maps & Geo
        "domain:maps.google.com", "domain:openstreetmap.org",
        "domain:earth.google.com", "domain:darksitefinder.com",
        "domain:justicemap.org",
        # Search
        "domain:duckduckgo.com", "domain:start.me",
        "domain:translate.google.com"
    ],
    "Travel & Transportation": [
        "domain:booking.com", "domain:airbnb.com", "domain:expedia.com",
        "domain:kayak.com", "domain:tripadvisor.com", "domain:vrbo.com",
        "domain:hotels.com", "domain:hotwire.com", "domain:priceline.com",
        "domain:travelocity.com", "domain:orbitz.com",
        "domain:uber.com", "domain:lyft.com", "domain:skyscanner.com",
        "domain:southwest.com", "domain:united.com", "domain:delta.com",
        "domain:aa.com", "domain:allegiantair.com", "domain:spiritairlines.com",
        "domain:amtrak.com", "domain:greyhound.com"
    ],
    "Food & Dining": [
        "domain:doordash.com", "domain:ubereats.com", "domain:grubhub.com",
        "domain:instacart.com", "domain:yelp.com", "domain:opentable.com",
        "domain:allrecipes.com", "domain:epicurious.com",
        "keyword:recipe", "keyword:restaurant", "keyword:cooking"
    ],
    "Health & Medical": [
        "domain:webmd.com", "domain:mayoclinic.org", "domain:healthline.com",
        "domain:nih.gov", "domain:cdc.gov", "domain:who.int",
        "domain:drugs.com", "domain:zocdoc.com", "domain:goodrx.com",
        "domain:rxlist.com", "domain:medlineplus.gov",
        "domain:myfitnesspal.com", "domain:strava.com",
        "domain:cernerhealth.com", "domain:mychart.com",
        "domain:myhealthrecord.com", "domain:clevelandclinic.org",
        "domain:medicatechusa.com",
        "keyword:dicom", "keyword:pacs", "keyword:x-ray", "keyword:radiology",
        "keyword:patient portal", "keyword:mychart"
    ],
    "Job Search & Career": [
        "domain:indeed.com", "domain:glassdoor.com", "domain:monster.com",
        "domain:ziprecruiter.com", "domain:dice.com", "domain:simplyhired.com",
        "domain:careerbuilder.com", "domain:roberthalf.com",
        "domain:upwork.com", "domain:fiverr.com", "domain:freelancer.com",
        "domain:governmentjobs.com", "domain:care.com",
        "domain:kellyservices.us", "domain:tbe.taleo.net",
        "domain:remoteok.com", "domain:levels.fyi",
        "domain:linkedin.com/jobs",
        "keyword:job opening", "keyword:careers at", "keyword:staffing",
        "keyword:resume", "keyword:hiring"
    ],
    "Real Estate": [
        "domain:zillow.com", "domain:realtor.com", "domain:redfin.com",
        "domain:trulia.com", "domain:apartments.com", "domain:rent.com",
        "domain:rocketmortgage.com", "domain:appfolio.com",
        "keyword:real estate", "keyword:for rent", "keyword:apartment"
    ],
    "Automotive": [
        "domain:cars.com", "domain:autotrader.com", "domain:cargurus.com",
        "domain:carmax.com", "domain:kbb.com", "domain:edmunds.com",
        "domain:truecar.com", "domain:vroom.com", "domain:carvana.com"
    ],
    "Sports": [
        "domain:espn.com", "domain:sports.yahoo.com", "domain:bleacherreport.com",
        "domain:nba.com", "domain:nfl.com", "domain:mlb.com", "domain:nhl.com",
        "domain:cbssports.com", "domain:foxsports.com", "domain:theathletic.com"
    ],
    "Government & Legal": [
        "regex:\\.gov(/|$)", "domain:usa.gov", "domain:irs.gov", "domain:ssa.gov",
        "domain:cms.gov", "domain:sec.gov", "domain:fda.gov",
        "domain:fcc.gov", "domain:ftc.gov",
        "domain:law.cornell.edu", "domain:findlaw.com",
        "domain:sunbiz.org", "domain:search.sunbiz.org",
        "domain:myflorida.com", "domain:flhsmv.gov", "domain:floridajobs.org"
    ],
    "Downloads & Torrents": [
        "domain:1337x.to", "domain:thepiratebay.org", "domain:rarbg.to",
        "domain:nyaa.si", "domain:fitgirl-repacks.site",
        "domain:thehouseofportable.com", "domain:filecr.com",
        "domain:rutracker.org", "domain:thegeeks.bz", "domain:torrentgalaxy.to",
        "domain:yts.mx", "domain:eztv.re", "domain:limetorrents.info",
        "domain:forum.mobilism.me", "domain:mobilism.me",
        "domain:mega.nz", "domain:mediafire.com", "domain:file-upload.org",
        "domain:fcportables.com", "domain:massgrave.dev",
        "keyword:torrent", "keyword:magnet", "keyword:seedbox",
        "keyword:nulled", "keyword:crack", "keyword:warez"
    ],
    "Media Production & Design": [
        # Video Equipment
        "domain:teradek.com", "domain:blackmagicdesign.com",
        "domain:obsproject.com", "domain:sbe.org",
        # Graphics & Templates
        "domain:gfxtra.com", "domain:gfxdrug.com", "domain:gfxdownload.com",
        "domain:intro-hd.net", "domain:freepreset.net", "domain:freevideoeffect.com",
        "domain:motionarray.com", "domain:envato.com", "domain:elements.envato.com",
        "domain:prodesigntools.com", "domain:helpx.adobe.com", "domain:adobe.com",
        "domain:creativecloud.adobe.com",
        # Stock Media
        "domain:pexels.com", "domain:unsplash.com", "domain:pixabay.com",
        "domain:shutterstock.com", "domain:gettyimages.com",
        "domain:videvo.net", "domain:artlist.io",
        # Design Tools
        "domain:dribbble.com", "domain:behance.net", "domain:99designs.com",
        "domain:brandcrowd.com", "domain:looka.com",
        "domain:freepik.com", "domain:flaticon.com", "domain:iconmonstr.com",
        "domain:icons8.com", "domain:fontawesome.com",
        "domain:dafont.com", "domain:fontsquirrel.com",
        "domain:pngwing.com", "domain:canva.com", "domain:figma.com",
        "keyword:after effects", "keyword:premiere pro", "keyword:stock footage",
        "keyword:videohive", "keyword:motion graphic"
    ],
    "Software & Customization": [
        # Windows Themes
        "domain:vsthemes.org", "domain:deviantart.com", "domain:windhawk.net",
        "domain:startallback.com", "domain:stardock.com", "domain:rainmeter.net",
        "keyword:theme", "keyword:wallpaper", "keyword:dark mode",
        # Applications
        "domain:ninite.com", "domain:portableapps.com", "domain:portablefreeware.com",
        "domain:majorgeeks.com", "domain:softpedia.com", "domain:filehippo.com",
        "domain:alternativeto.net", "domain:wingetgui.com",
        "domain:voidtools.com", "domain:freewaregenius.com",
        "domain:mozilla.org", "domain:7-zip.org", "domain:notepad-plus-plus.org",
        "domain:videolan.org", "domain:handbrake.fr", "domain:audacity.org",
        "domain:gimp.org", "domain:inkscape.org", "domain:libreoffice.org"
    ],
    "Productivity & Tools": [
        # Google Workspace
        "domain:docs.google.com", "domain:drive.google.com",
        "domain:sheets.google.com", "domain:slides.google.com",
        "domain:keep.google.com", "domain:calendar.google.com",
        "domain:sites.google.com", "domain:photos.google.com",
        "domain:fonts.google.com",
        # Email & Communication
        "domain:mail.google.com", "domain:outlook.live.com",
        "domain:outlook.office.com", "domain:login.live.com",
        "domain:mail.yahoo.com", "domain:messages.google.com",
        # Online Tools
        "domain:notion.so", "domain:trello.com", "domain:asana.com",
        "domain:airtable.com", "domain:feedly.com",
        "domain:iloveimg.com", "domain:ilovepdf.com", "domain:ezgif.com",
        "domain:cloudconvert.com",
        "domain:hubspot.com"
    ],
}

