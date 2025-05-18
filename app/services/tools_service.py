"""
Services for handling tool invocations from Ultravox.
"""
import json
import traceback
import websockets
from twilio.rest import Client
#from pinecone_plugins.assistant.models.chat import Message
from app.core.shared_state import sessions
from app.services.n8n_service import send_to_webhook, send_transcript_to_n8n
from app.utils.websocket_utils import safe_close_websocket
from app.core.prompts import get_stage_prompt, get_stage_voice
from app.core.config import (
    CALENDARS_LIST,
    TWILIO_ACCOUNT_SID,
    TWILIO_AUTH_TOKEN,
    PINECONE_API_KEY
)

async def handle_tool_invocation(uv_ws, toolName, invocationId, parameters):
    """
    Helper function to handle tool invocations detected in transcripts or direct invocations
    """
    print(f"Processing tool invocation: {toolName} with invocationId: {invocationId} and parameters: {parameters}")
    
    if toolName == "question_and_answer":
        print("Q&A tool skipped: Pinecone not available")
        tool_result = {
        "type": "client_tool_result",
        "invocationId": invocationId,
        "result": "Sorry, I cannot answer that question right now.",
        "response_type": "tool-response"
    }
        await uv_ws.send(json.dumps(tool_result))
        return

    
    elif toolName == "verify":
        print(f'Verifying customer identity with parameters: {parameters}')
        # Extract verification parameters
        full_name = parameters.get('full_name', '')
        date_of_birth = parameters.get('date_of_birth', '')
        policy_number = parameters.get('policy_number', '')
        
        # This is a mock verification - in a real system, you would check against a database
        # For demo purposes, we'll consider verification successful if all fields are provided
        verification_successful = all([full_name, date_of_birth, policy_number])
        
        # Send verification result back to the agent
        verification_result = "Confirmed" if verification_successful else "Not Confirmed"
        tool_result = {
            "type": "client_tool_result",
            "invocationId": invocationId,
            "result": verification_result,
            "response_type": "tool-response"
        }
        print(f"Verification result: {verification_result}")
        await uv_ws.send(json.dumps(tool_result))
    
    elif toolName == "calendar_book":
        print(f"📅 Invoked 'calendar_book' with params: {parameters}")

        # Extract from Ultravox params
        name = parameters.get("name")
        email = parameters.get("email")
        purpose = parameters.get("purpose")
        datetime_str = parameters.get("datetime")
        calendar_id = parameters.get("calendar_id")

        if not all([name, email, purpose, datetime_str, calendar_id]):
            msg = "Missing parameters for booking. Need: name, email, purpose, datetime, calendar_id."
            print(msg)
            await uv_ws.send(json.dumps({
                "type": "client_tool_result",
                "invocationId": invocationId,
                "result": msg,
                "response_type": "tool-response"
            }))
            return

        # 🔗 Send to n8n webhook
        call_sid = None
        session = None
        for sid, sess in sessions.items():
            if sess.get("uv_ws") == uv_ws:
                call_sid = sid
                session = sess
                break

        payload = {
            "route": "3",
            "number": session.get("callerNumber", "Unknown"),
            "data": json.dumps({
                "name": name,
                "email": email,
                "purpose": purpose,
                "datetime": datetime_str,
                "calendar_id": calendar_id
            })
        }

        try:
            webhook_response = await send_to_webhook(payload)
            result = json.loads(webhook_response).get("message", "Booking confirmed.")

            await uv_ws.send(json.dumps({
                "type": "client_tool_result",
                "invocationId": invocationId,
                "result": result,
                "response_type": "tool-response"
            }))
        except Exception as e:
            print(f"❌ Error in calendar_book: {e}")
            await uv_ws.send(json.dumps({
                "type": "client_tool_result",
                "invocationId": invocationId,
                "error_type": "booking_error",
                "error_message": "Calendar booking failed due to a server error."
            }))


    #meeting handling
    elif toolName == "schedule_meeting":
        print(f'Arguments passed to schedule_meeting tool: {parameters}')
        # Validate required parameters
        required_params = ["name", "email", "purpose", "datetime", "location"]
        missing_params = [param for param in required_params if not parameters.get(param)]

        if missing_params:
            print(f"Missing parameters for schedule_meeting: {missing_params}")

            # Inform the agent to prompt the user for missing parameters
            prompt_message = f"Please provide the following information to schedule your meeting: {', '.join(missing_params)}."
            tool_result = {
                "type": "client_tool_result",
                "invocationId": invocationId,
                "result": prompt_message,
                "response_type": "tool-response"
            }
            await uv_ws.send(json.dumps(tool_result))
        else:
            await handle_schedule_meeting(uv_ws, None, invocationId, parameters)
    
    elif toolName == "escalate_to_manager":
        print(f'Escalating to manager with parameters: {parameters}')
        issue_type = parameters.get('issue_type', '')
        issue_details = parameters.get('issue_details', '')
        customer_name = parameters.get('customer_name', '')
        
        # Get manager stage system prompt
        manager_prompt = get_stage_prompt('manager')
        manager_voice = get_stage_voice('manager')
        
        # The transfer intro is handled by the AI, we don't need to include it in the toolResultText
        # Instead, we'll provide a greeting from the manager directly
        manager_greeting = f"You're now speaking with Alex, the Senior Manager at SecureLife Insurance. I've been briefed on your situation{', ' + customer_name if customer_name else ''}. You're concerned about {issue_type}. How can I help you today?"
        
        # Prepare tool result with stage transition
        stage_result = {
            "type": "client_tool_result",
            "invocationId": invocationId,
            "result": json.dumps({
                "systemPrompt": manager_prompt,
                "voice": manager_voice,
                "toolResultText": manager_greeting
            }),
            "response_type": "new-stage"
        }
        
        print(f"Transitioning to manager stage with voice: {manager_voice}")
        await uv_ws.send(json.dumps(stage_result))
    
    # Return to claim handling is no longer a separate tool according to the diagram
    # The manager can return the customer to claim handling as a direct transition
    
    elif toolName == "move_to_call_summary":
        print(f'Moving to call summary stage with parameters: {parameters}')
        # Get call summary stage system prompt
        summary_prompt = get_stage_prompt('call_summary')
        summary_voice = get_stage_voice('call_summary')
        
        # Create stage transition response
        stage_transition_msg = "Before we conclude our call, let me summarize what we've discussed and next steps."
        
        # Prepare tool result with stage transition
        stage_result = {
            "type": "client_tool_result",
            "invocationId": invocationId,
            "result": json.dumps({
                "systemPrompt": summary_prompt,
                "voice": summary_voice,
                "toolResultText": stage_transition_msg
            }),
            "response_type": "new-stage"
        }
        
        print(f"Transitioning to call summary stage with voice: {summary_voice}")
        await uv_ws.send(json.dumps(stage_result))
    
    elif toolName == "hangUp":
        print("Received hangUp tool invocation")
        # Get the call_sid and session from the global sessions dictionary
        call_sid = None
        session = None
        
        # Find the session for this websocket connection
        for sid, sess in sessions.items():
            if sess.get('uv_ws') == uv_ws:
                call_sid = sid
                session = sess
                break
        
        print(f"Ending call from hangUp tool invocation (CallSid={call_sid})")
        
        # Update the session's state to indicate the call is ending
        if session:
            # Indicate that we're in the process of hanging up
            session['hanging_up'] = True
        
        try:
            # First send success response before closing WebSocket
            tool_result = {
                "type": "client_tool_result",
                "invocationId": invocationId,
                "result": "Call ended successfully",
                "response_type": "tool-response"
            }
            # Get the WebSocket state flag from the calling function if available
            ultravox_active = session.get('ultravox_ws_active', True) if session else True
            
            if ultravox_active and uv_ws and uv_ws.state == websockets.protocol.State.OPEN:
                await uv_ws.send(json.dumps(tool_result))
                # If we're in the media_stream function, update the state
                if 'ultravox_ws_active' in session:
                    session['ultravox_ws_active'] = False
        except Exception as e:
            print(f"Error sending hangUp response: {e}")
        
        try:
            # End Twilio call if we have a call_sid
            if call_sid:
                client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
                
                # Ensure call_sid is properly formatted
                call_sid_str = str(call_sid)
                if len(call_sid_str) > 34 and 'CA' in call_sid_str:
                    start_idx = call_sid_str.find('CA')
                    extracted_sid = call_sid_str[start_idx:start_idx+34]
                    if len(extracted_sid) == 34:
                        call_sid = extracted_sid
                
                # Fetch the call and end it
                call = client.calls(call_sid).fetch()
                client.calls(call_sid).update(status='completed')
                print(f"Successfully ended Twilio call: {call_sid}")
            
                # Send transcript to N8N and cleanup session
                if session:
                    # Only send transcript if it hasn't been sent already
                    if not session.get('transcript_sent', False):
                        await send_transcript_to_n8n(session)
                    # Don't remove session here, it will be removed in media_stream.py
        except Exception as e:
            print(f"Error ending Twilio call: {e}")
            traceback.print_exc()
        
        # Finally, close Ultravox WebSocket using our safe utility
        await safe_close_websocket(uv_ws, name="Ultravox WebSocket (hangUp)")
    else:
        print(f"Unknown tool: {toolName}")


async def handle_question_and_answer(uv_ws, invocationId: str, question: str):
    print("Pinecone is not available. Skipping question_and_answer tool.")

    tool_result = {
        "type": "client_tool_result",
        "invocationId": invocationId,
        "result": "Sorry, I can't answer that question right now.",
        "response_type": "tool-response"
    }
    await uv_ws.send(json.dumps(tool_result))
            
async def handle_schedule_meeting(uv_ws, session, invocationId: str, parameters):
    """
    Uses N8N to finalize a meeting schedule.
    """
    try:
        name = parameters.get("name")
        email = parameters.get("email")
        purpose = parameters.get("purpose")
        datetime_str = parameters.get("datetime")
        location = parameters.get("location")

        print(f"Received schedule_meeting parameters: name={name}, email={email}, purpose={purpose}, datetime={datetime_str}, location={location}")

        # Validate parameters
        if not all([name, email, purpose, datetime_str, location]):
            raise ValueError("One or more required parameters are missing.")
        
        calendars = CALENDARS_LIST
        calendar_id = calendars.get(location, None)
        if not calendar_id:
            raise ValueError(f"Invalid location: {location}")

        data = {
            "name": name,
            "email": email,
            "purpose": purpose,
            "datetime": datetime_str,
            "calendar_id": calendar_id
        }

        # Fire off the scheduling request to N8N
        payload = {
            "route": "3",
            "number": session.get("callerNumber", "Unknown"),
            "data": json.dumps(data)
        }
        print(f"Sending payload to N8N: {json.dumps(payload, indent=2)}")
        webhook_response = await send_to_webhook(payload)
        parsed_response = json.loads(webhook_response)
        booking_message = parsed_response.get('message', 
            "I'm sorry, I couldn't schedule the meeting at this time.")

        # Return the final outcome to Ultravox
        tool_result = {
            "type": "client_tool_result",
            "invocationId": invocationId,
            "result": booking_message,
            "response_type": "tool-response"
        }
        await uv_ws.send(json.dumps(tool_result))
        print(f"Sent schedule_meeting result to Ultravox: {booking_message}")

    except Exception as e:
        print(f"Error scheduling meeting: {e}")
        # Send error result back to Ultravox
        error_result = {
            "type": "client_tool_result",
            "invocationId": invocationId,
            "error_type": "implementation-error",
            "error_message": "An error occurred while scheduling your meeting."
        }
        await uv_ws.send(json.dumps(error_result))
        print("Sent error message for schedule_meeting to Ultravox.")
