"""
Services for interacting with Ultravox voice AI.
"""
import json
import httpx
import requests
from app.core.prompts import get_personalized_system_message
from app.core.config import (
    ULTRAVOX_API_KEY,
    ULTRAVOX_MODEL, 
    ULTRAVOX_VOICE, 
    ULTRAVOX_SAMPLE_RATE,
    ULTRAVOX_BUFFER_SIZE
)




async def create_ultravox_call(system_prompt: str, first_message: str, agent_id: str, voice: str) -> str:
    """
    Creates a new Ultravox call in serverWebSocket mode and returns the joinUrl.
    """
    url = "https://api.ultravox.ai/api/calls"
    headers = {
        "X-API-Key": ULTRAVOX_API_KEY,
        "Content-Type": "application/json"


    }
    print("📞 check_returning_user number:", agent_id)


    payload = {
        "systemPrompt": system_prompt,
        "model": ULTRAVOX_MODEL,
        "voice": voice,
        "temperature": 0.1,
        "initialMessages": [
            {
                "role": "MESSAGE_ROLE_USER",
                "text": first_message
            }
        ],
        "medium": {
            "serverWebSocket": {
                "inputSampleRate": ULTRAVOX_SAMPLE_RATE,
                "outputSampleRate": ULTRAVOX_SAMPLE_RATE,
                "clientBufferSizeMs": ULTRAVOX_BUFFER_SIZE
            }
        },
        "vadSettings": {
            "turnEndpointDelay": "0.384s",
            "minimumTurnDuration": "0s",
            "minimumInterruptionDuration": "0.09s"
        },
        "selectedTools": [
        {
           "temporaryTool": {
               "modelToolName": "check_returning_user",
               "description": "Check if the caller has previously interacted and return a personalized greeting if found.",
               "dynamicParameters": [
                   {
                       "name": "caller_number",
                       "location": 4,                
                       "schema": { "type": "string", "description": "Phone number of the caller" },
                       "required": True
                   }
               ],
                
               "timeout": "10s",
              "http": {
             "url": "https://harbormoor.app.n8n.cloud/webhook/route1",
             "httpMethod": "POST"
           }
           }
           
       },         
          
             {
                "temporaryTool": {
                    "modelToolName": "schedule_meeting",
                    "description": "Schedule a meeting for a customer. Returns a message indicating whether the booking was successful or not.",
                    "dynamicParameters": [
                        {
                            "name": "name",
                            "location": 4,
                            "schema": {
                                "type": "string",
                                "description": "Customer's full name"
                            },
                            "required": True
                        },
                        {
                            "name": "email",
                            "location": 4,
                            "schema": {
                                "type": "string",
                                "description": "Customer's email"
                            },
                            "required": True
                        },
                        {
                            "name": "purpose",
                            "location": 4,
                            "schema": {
                                "type": "string",
                                "description": "Purpose of the Meeting"
                            },
                            "required": True
                        },
                        {
                            "name": "datetime",
                            "location": 4,
                            "schema": {
                                "type": "string",
                                "description": "Meeting Datetime"
                            },
                            
                            "required": True
                        },
                        {
        "name": "calendar_id",
        "location": 4,
        "schema": {
          "type": "string",
          "description": "ID of the calendar to schedule the meeting in"
        },
         "required": True
                        }
                    ],
                    "timeout": "20s",
           "http": {
             "url": "https://harbormoor.app.n8n.cloud/webhook/route3",
             "httpMethod": "POST",
           }
                }
            }
        ],
        "tool_choice": "auto",
       "metadata": {
           "caller_number": agent_id
       }
    }

    print(f"📞 Using caller_number = {agent_id}")
    print("📤 Payload being sent to Ultravox:")
    print(json.dumps(payload, indent=2))

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(url, headers=headers, json=payload)
            resp.raise_for_status()  # ✅ <-- Add this line here

                        # ── DEBUG ──
            print("🧨 Ultravox Response Status:", resp.status_code)
            try:
                print("🧨 Ultravox Response Body:", resp.json())
            except Exception:
                print("🧨 Ultravox Response Text:", await resp.text())
            # ───────────



        

        body = resp.json()
        join_url = body.get("joinUrl", "")
        print("Ultravox joinUrl received:", join_url)
        return join_url
    except Exception as e:
        print("Ultravox create call request failed:", str(e))
        print("Failed Payload:", json.dumps(payload, indent=2))
        return ""
