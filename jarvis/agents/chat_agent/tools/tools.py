# Tool definitions for ChatAgent

tools = [
    {
        "type": "function",
        "function": {
            "name": "store_fact",
            "description": "Remember a fact about the user",
            "parameters": {
                "type": "object",
                "properties": {
                    "fact": {"type": "string"}
                },
                "required": ["fact"]
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_facts",
            "description": "ONLY use this to recall user-specific facts and preferences that were previously stored. "
                          "NEVER use this for general knowledge questions like geography, history, science, literature, "
                          "or any factual information that is publicly known. For general knowledge questions, "
                          "answer directly from your own knowledge without calling this tool. "
                          "Only use get_facts when the user asks about something they explicitly told you "
                          "(e.g., 'what's my favorite color', 'what's my dog's name'). "
                          "If you mistakenly call this and get no results, you MUST answer the question from your own knowledge.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "top_k": {"type": "integer", "default": 3},
                },
                "required": ["query"]
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_profile",
            "description": "Update a field in the user profile",
            "parameters": {
                "type": "object",
                "properties": {
                    "field": {"type": "string"},
                    "value": {"type": "string"}
                },
                "required": ["field", "value"]
            },
        },
    },
]
