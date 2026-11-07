"""Keep distinct host offers separate without dropping pending inputs."""
def select_turn_messages(messages):
    if not messages:
        return []
    offer = messages[0].get('attention_offer')
    return [message for message in messages if message.get('attention_offer') == offer]
