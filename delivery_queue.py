"""Keep distinct host offers separate without dropping pending inputs."""
def select_turn_messages(messages):
    if not messages:
        return []
    offer = messages[0].get('attention_offer')
    return [message for message in messages if message.get('attention_offer') == offer
            and message.get('reply_scope') == messages[0].get('reply_scope')]


def optional_reply(messages):
    return bool(messages.get("attention_offer") or messages.get("source") in ("agent", "activity", "follow_up"))


async def due_follow_up(request, state):
    """Use the existing reply allowance; never connect a model merely to poll."""
    if not state.get('follow_up_pending') or state.get('busy') or state.get('turn_active'):
        return []
    # Incoming conversation takes precedence over a self-authored reminder.
    queued = await request('/inbox/peek')
    if any(m.get('source') != 'follow_up' for m in queued):
        return []
    admission = await request('/conversation/admission')
    if admission.get('remaining') == 0:
        return []
    await request('/conversation/follow-up/poll', {})
    admission = await request('/conversation/admission')
    if admission.get('remaining') == 0:
        return []
    eligible = set(admission.get('eligible_ids', []))
    return [m for m in await request('/inbox/peek')
            if m.get('source') == 'follow_up' and m.get('id') in eligible][:1]


def attention_reply_messages(messages, eligible_ids):
    """Optional delivery never reserves an autonomous work turn.

    None means ordinary input. An empty list leaves an ineligible offer queued;
    the controller may continue separately authorized work without that offer.
    No ticket is stripped, claimed again, or treated as fulfilled.
    """
    if not any(optional_reply(message) for message in messages):
        return None
    eligible = set(eligible_ids)
    return messages if all(message.get('id') in eligible for message in messages) else []
