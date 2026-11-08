"""Keep distinct host offers separate without dropping pending inputs."""
def select_turn_messages(messages):
    if not messages:
        return []
    offer = messages[0].get('attention_offer')
    return [message for message in messages if message.get('attention_offer') == offer]


def attention_reply_messages(messages, eligible_ids):
    """Optional delivery never reserves an autonomous work turn.

    None means ordinary input. An empty list leaves an ineligible offer queued;
    the controller may continue separately authorized work without that offer.
    No ticket is stripped, claimed again, or treated as fulfilled.
    """
    if not any(message.get('attention_offer') for message in messages):
        return None
    eligible = set(eligible_ids)
    return messages if all(message.get('id') in eligible for message in messages) else []
