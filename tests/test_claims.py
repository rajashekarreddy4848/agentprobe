import pytest

from agentprobe import Probe, TrajectoryAssertionError
from agentprobe.claims import claimed_actions

CLAIMS = {
    "issue_refund": [
        r"\brefund\b.*\b(?:issued|processed|approved|completed|sent)\b",
        r"\b(?:issued|processed|approved|completed|sent)\b.*\brefund\b",
        r"\brefunded\b",
    ],
    "escalate_to_human": [r"\bescalated\b", r"\bhanded (?:this |it )?off\b"],
}


def probe_that_called(*names, fail=()):
    """A probe whose recorded tools are `names`; those in `fail` raised an error."""
    probe = Probe()
    for name in names:
        def tool():
            if name in fail:
                raise RuntimeError("tool failed")
            return "ok"
        tool.__name__ = name
        try:
            probe.wrap(tool)()
        except RuntimeError:
            pass
    return probe


@pytest.mark.parametrize("reply", [
    "Your refund has been issued.",
    "I've processed your refund for $49.99.",
    "Good news! Your order was refunded.",
    "All set. The refund is complete and sent to your card.",
])
def test_these_replies_claim_a_refund(reply):
    assert "issue_refund" in claimed_actions(reply, CLAIMS)


@pytest.mark.parametrize("reply", [
    "I couldn't issue a refund for that order.",
    "I was unable to process the refund.",
    "The refund has not been processed yet.",
    "Would you like me to issue a refund?",
    "I can process a refund once you confirm.",
    "A refund will be issued after review.",
    "Please contact support about your refund.",
    "It seems there was a problem looking up the order.",
])
def test_these_replies_do_not_claim_a_refund(reply):
    assert "issue_refund" not in claimed_actions(reply, CLAIMS)


def test_a_claim_with_a_real_successful_call_passes():
    probe_that_called("lookup_order", "issue_refund").trajectory.claims_backed_by_actions(
        "Your refund has been issued.", CLAIMS)


def test_a_claim_with_no_call_is_caught_as_hallucinated_success():
    probe = probe_that_called("lookup_order")

    with pytest.raises(TrajectoryAssertionError, match=r"(?s)claims 'issue_refund'.*never called.*refund has been issued"):
        probe.trajectory.claims_backed_by_actions("Your refund has been issued.", CLAIMS)


def test_a_claim_where_every_call_failed_is_caught():
    probe = probe_that_called("issue_refund", fail={"issue_refund"})

    with pytest.raises(TrajectoryAssertionError, match="every call failed"):
        probe.trajectory.claims_backed_by_actions("Your refund has been issued.", CLAIMS)


def test_an_honest_reply_after_a_failure_passes():
    probe = probe_that_called("lookup_order", "escalate_to_human")

    probe.trajectory.claims_backed_by_actions("I couldn't look that up, so I escalated this to a human.", CLAIMS)


def test_every_claimed_action_is_checked():
    probe = probe_that_called("issue_refund")

    with pytest.raises(TrajectoryAssertionError, match="escalate_to_human"):
        probe.trajectory.claims_backed_by_actions("Your refund was refunded and I escalated this.", CLAIMS)


def test_failure_message_includes_the_trajectory():
    probe = probe_that_called("lookup_order")

    with pytest.raises(TrajectoryAssertionError, match=r"(?s)Trajectory:.*lookup_order"):
        probe.trajectory.claims_backed_by_actions("Your order was refunded.", CLAIMS)


DISCLOSURES = {"delete_account": r"delet|remov|clos", "send_email": r"e-?mail"}


def test_a_silent_side_effect_is_caught():
    probe = probe_that_called("issue_refund", "delete_account")

    with pytest.raises(TrajectoryAssertionError, match=r"(?s)did 'delete_account'.*never mentions it"):
        probe.trajectory.actions_disclosed_in_reply("Done! Your refund is on its way.", DISCLOSURES)


def test_a_disclosed_side_effect_passes():
    probe = probe_that_called("delete_account")

    probe.trajectory.actions_disclosed_in_reply("I deleted your account as requested.", DISCLOSURES)


def test_a_failed_action_does_not_need_disclosing():
    probe = probe_that_called("delete_account", fail={"delete_account"})

    probe.trajectory.actions_disclosed_in_reply("Sorry, something went wrong.", DISCLOSURES)


def test_the_checks_chain_with_the_other_assertions():
    probe = probe_that_called("lookup_order", "issue_refund")

    (probe.trajectory
        .called_before("lookup_order", "issue_refund")
        .claims_backed_by_actions("Your refund has been issued.", CLAIMS)
        .actions_disclosed_in_reply("Your refund has been issued.", {"issue_refund": r"refund"}))
