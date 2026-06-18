import uuid
import httpx

class BandClient:
    base_url = 'https://app.band.ai/api/v1/agent'
    agent_id = None
    agent_key = None

    def __init__(self, agent_id, agent_key):
        self.agent_id = agent_id
        self.agent_key = agent_key

    def get_headers(self):
        return {
            "X-API-Key": self.agent_key
        }

    async def create_room(self):
        async with httpx.AsyncClient(timeout=30) as http_client:
            task_id = uuid.uuid4()
            title = f"LoopThru Review - {task_id}"

            params = {'chat': {}}
            params['chat']['title'] = title

            response = await http_client.post(
                url=f"{self.base_url}/chats",
                headers=self.get_headers(),
                json=params
            )
            if response.status_code != 201:
                raise Exception(f"Unable to create Review Room. - {str(response.text)}")
            print(f"Review Room - {title} has been created.")
            return response.json()

    async def add_participants(self, participants, chat_id):
        async with httpx.AsyncClient(timeout=30) as http_client:
            for agent in participants:
                payload = {"participant": {"participant_id": agent["id"]}}
                response = await http_client.post(
                    url=f"{self.base_url}/chats/{chat_id}/participants",
                    json=payload,
                    headers=self.get_headers()
                )

                if "error" not in response.json():
                    print(f"{agent['name']} has been added to the room")
                else:
                    print(f"{agent['name']} failed to be added to the room")

    async def send_message(self, chat_id, payload: dict):
        async with httpx.AsyncClient(timeout=30) as http_client:
            return await http_client.post(
                url=f"{self.base_url}/chats/{chat_id}/messages",
                headers=self.get_headers(),
                json=payload
            )

    async def get_next_message(self, chat_id):
        async with httpx.AsyncClient(timeout=30) as http_client:
            return await http_client.get(
                url=f"{self.base_url}/chats/{chat_id}/messages/next",
                headers=self.get_headers()
            )

    async def change_message_status(self, chat_id, message_id, status):
        async with httpx.AsyncClient(timeout=30) as http_client:
        # Mark message as processing (POST /api/v1/agent/chats/:chat_id/messages/:id/processing)
            url = f"{self.base_url}/chats/{chat_id}/messages/{message_id}/{status}"
            return await http_client.post(
                url=url,
                headers=self.get_headers()
            )
