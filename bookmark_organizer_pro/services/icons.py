"""Built-in icon catalog and category icon suggestion helpers."""

from __future__ import annotations

from typing import Dict, List


# =============================================================================
# Icon Library
# =============================================================================
class IconLibrary:
    """Built-in icon library with common icons"""
    
    # Organized icon collection (using emoji as icons)
    ICONS = {
        "Files & Folders": {
            "folder": "📁", "folder_open": "📂", "file": "📄", "document": "📃",
            "clipboard": "📋", "archive": "🗃️", "cabinet": "🗄️", "briefcase": "💼"
        },
        "Communication": {
            "email": "📧", "envelope": "✉️", "chat": "💬", "phone": "📱",
            "megaphone": "📢", "bell": "🔔", "comment": "💭", "mail": "📨"
        },
        "Technology": {
            "laptop": "💻", "desktop": "🖥️", "keyboard": "⌨️", "mouse": "🖱️",
            "globe": "🌐", "link": "🔗", "database": "🗄️", "server": "🖲️",
            "code": "💻", "terminal": "⬛", "bug": "🐛", "robot": "🤖"
        },
        "Media": {
            "photo": "📷", "video": "📹", "music": "🎵", "film": "🎬",
            "headphones": "🎧", "mic": "🎤", "tv": "📺", "radio": "📻"
        },
        "Business": {
            "chart_up": "📈", "chart_down": "📉", "chart": "📊", "money": "💰",
            "card": "💳", "bank": "🏦", "shopping": "🛒", "gift": "🎁"
        },
        "Tools": {
            "wrench": "🔧", "hammer": "🔨", "gear": "⚙️", "tools": "🛠️",
            "lightbulb": "💡", "magnifier": "🔍", "lock": "🔒", "key": "🔑"
        },
        "Status": {
            "check": "✅", "cross": "❌", "warning": "⚠️", "info": "ℹ️",
            "question": "❓", "star": "⭐", "heart": "❤️", "fire": "🔥"
        },
        "Navigation": {
            "home": "🏠", "building": "🏢", "pin": "📍", "map": "🗺️",
            "compass": "🧭", "flag": "🚩", "bookmark": "🔖", "tag": "🏷️"
        },
        "Education": {
            "book": "📚", "notebook": "📓", "pencil": "✏️", "pen": "🖊️",
            "graduation": "🎓", "science": "🔬", "calculator": "🧮", "abc": "🔤"
        },
        "Nature": {
            "sun": "☀️", "moon": "🌙", "cloud": "☁️", "tree": "🌳",
            "flower": "🌸", "earth": "🌍", "mountain": "⛰️", "water": "💧"
        },
        "People": {
            "user": "👤", "users": "👥", "person": "🧑", "team": "👨‍👩‍👧‍👦",
            "handshake": "🤝", "thumbs_up": "👍", "clap": "👏", "wave": "👋"
        },
        "Time": {
            "clock": "🕐", "calendar": "📅", "hourglass": "⏳", "alarm": "⏰",
            "stopwatch": "⏱️", "timer": "⏲️", "history": "🕰️", "schedule": "📆"
        }
    }
    
    @classmethod
    def get_all_icons(cls) -> Dict[str, Dict[str, str]]:
        """Get all icons organized by category"""
        return cls.ICONS
    
    @classmethod
    def get_flat_icons(cls) -> Dict[str, str]:
        """Get all icons as flat dict"""
        flat = {}
        for category_icons in cls.ICONS.values():
            flat.update(category_icons)
        return flat
    
    @classmethod
    def search_icons(cls, query: str) -> Dict[str, str]:
        """Search icons by name"""
        query = query.lower()
        results = {}
        
        for category_icons in cls.ICONS.values():
            for name, icon in category_icons.items():
                if query in name.lower():
                    results[name] = icon
        
        return results
    
    @classmethod
    def suggest_icon(cls, text: str) -> str:
        """Suggest an icon based on text"""
        text_lower = text.lower()
        
        # Keywords to icon mapping
        keyword_map = {
            "code": "💻", "dev": "💻", "program": "💻", "software": "💻",
            "doc": "📄", "document": "📄", "file": "📄", "paper": "📄",
            "video": "📹", "movie": "🎬", "film": "🎬", "youtube": "📺",
            "music": "🎵", "audio": "🎵", "sound": "🎵", "spotify": "🎵",
            "photo": "📷", "image": "📷", "picture": "📷", "instagram": "📷",
            "mail": "📧", "email": "📧", "gmail": "📧", "outlook": "📧",
            "shop": "🛒", "store": "🛒", "buy": "🛒", "amazon": "🛒",
            "news": "📰", "article": "📰", "blog": "📝", "read": "📖",
            "game": "🎮", "play": "🎮", "gaming": "🎮", "steam": "🎮",
            "social": "👥", "facebook": "👥", "twitter": "🐦", "linkedin": "💼",
            "github": "🐙", "git": "🐙", "repo": "📦", "code": "💻",
            "ai": "🤖", "ml": "🤖", "machine": "🤖", "learning": "🎓",
            "finance": "💰", "money": "💰", "bank": "🏦", "invest": "📈",
            "travel": "✈️", "trip": "✈️", "vacation": "🏖️", "hotel": "🏨",
            "food": "🍕", "recipe": "🍳", "restaurant": "🍽️", "cook": "👨‍🍳",
            "health": "💊", "medical": "🏥", "doctor": "👨‍⚕️", "fitness": "💪",
            "education": "🎓", "learn": "📚", "course": "📖", "school": "🏫",
            "work": "💼", "job": "💼", "career": "👔", "office": "🏢",
        }
        
        for keyword, icon in keyword_map.items():
            if keyword in text_lower:
                return icon
        
        return "📁"  # Default folder icon


# =============================================================================
# Auto-Icon Suggestion (AI-powered)
# =============================================================================
class AIIconSuggester:
    """Suggest icons for categories using AI or keyword matching"""
    
    KEYWORD_ICONS = {
        # Technology
        "code": "💻", "programming": "💻", "developer": "💻", "software": "💻",
        "github": "🐙", "git": "🐙", "repository": "📦",
        "api": "🔌", "database": "🗄️", "server": "🖥️", "cloud": "☁️",
        "security": "🔒", "network": "🌐", "web": "🌐", "internet": "🌐",
        
        # AI/ML
        "ai": "🤖", "artificial": "🤖", "machine learning": "🧠", "ml": "🧠",
        "neural": "🧠", "deep learning": "🧠", "data science": "📊",
        
        # Design
        "design": "🎨", "ui": "🎨", "ux": "🎨", "graphic": "🎨",
        "photo": "📷", "image": "🖼️", "video": "🎬", "audio": "🎵",
        
        # Business
        "business": "💼", "work": "💼", "career": "👔", "job": "💼",
        "finance": "💰", "money": "💵", "invest": "📈", "stock": "📈",
        "marketing": "📢", "sales": "🤝", "customer": "👥",
        
        # Education
        "education": "🎓", "learn": "📚", "course": "📖", "tutorial": "📝",
        "school": "🏫", "university": "🎓", "research": "🔬",
        
        # Entertainment
        "game": "🎮", "gaming": "🎮", "movie": "🎬", "music": "🎵",
        "book": "📚", "reading": "📖", "news": "📰", "blog": "📝",
        
        # Social
        "social": "👥", "community": "👥", "forum": "💬", "chat": "💬",
        "twitter": "🐦", "facebook": "👤", "linkedin": "💼",
        
        # Shopping
        "shop": "🛒", "store": "🏪", "buy": "🛍️", "amazon": "📦",
        "deal": "🏷️", "coupon": "🎟️",
        
        # Travel
        "travel": "✈️", "trip": "🧳", "hotel": "🏨", "flight": "✈️",
        "vacation": "🏖️", "map": "🗺️",
        
        # Health
        "health": "💊", "medical": "🏥", "fitness": "💪", "exercise": "🏃",
        "diet": "🥗", "nutrition": "🍎",
        
        # Food
        "food": "🍕", "recipe": "🍳", "restaurant": "🍽️", "cooking": "👨‍🍳",
        "coffee": "☕", "drink": "🥤",
    }
    
    @classmethod
    def suggest_icon(cls, category_name: str) -> str:
        """Suggest an icon based on category name"""
        name_lower = category_name.lower()
        
        # Check keyword matches
        for keyword, icon in cls.KEYWORD_ICONS.items():
            if keyword in name_lower:
                return icon
        
        # Check partial matches
        for keyword, icon in cls.KEYWORD_ICONS.items():
            if any(word in name_lower for word in keyword.split()):
                return icon
        
        # Use IconLibrary for broader matching
        flat_icons = IconLibrary.get_flat_icons()
        for icon_name, icon in flat_icons.items():
            if icon_name.replace('_', ' ') in name_lower or name_lower in icon_name:
                return icon
        
        # Default folder icon
        return "📁"
    
    @classmethod
    def suggest_multiple(cls, category_name: str, count: int = 5) -> List[str]:
        """Suggest multiple icon options"""
        suggestions = []
        name_lower = category_name.lower()
        
        # Collect all matching icons
        for keyword, icon in cls.KEYWORD_ICONS.items():
            if keyword in name_lower or any(w in name_lower for w in keyword.split()):
                if icon not in suggestions:
                    suggestions.append(icon)
        
        # Add defaults if needed
        defaults = ["📁", "📂", "🗂️", "📋", "🔖"]
        for icon in defaults:
            if icon not in suggestions:
                suggestions.append(icon)
        
        return suggestions[:count]
