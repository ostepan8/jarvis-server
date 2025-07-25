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
            "description": "Recall remembered facts matching a query",
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
