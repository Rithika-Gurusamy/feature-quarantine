import re
from typing import Tuple, List, Dict, Any
from app.models.schemas import CandidateProfile, MessageItem, IntentType

class IntentClassifier:
    """
    Classifies candidate messages into structured intent types:
    - PROFILE_QUERY: Questions about resume, skills, listed projects, name, contact info.
    - INTERVIEW_META_QUERY: Questions about interview timing, status, repeating questions.
    - GENERAL_CONVERSATION: Greetings, thanks, polite conversational remarks.
    - TECHNICAL_ANSWER: Candidate explaining architecture, design, code, tradeoffs.
    """
    @staticmethod
    def classify(message: str) -> IntentType:
        msg_clean = message.strip().lower()

        # Meta & Status queries
        if re.search(r"\b(time (left|remaining)|how much time|repeat (the )?question|what was the question|what time|duration)\b", msg_clean):
            return "INTERVIEW_META_QUERY"

        # Profile queries (asking about their own resume / background)
        if (
            re.search(r"\b(what('?s| is) my name|who am i|my name|what (are )?my skills|what (projects?|experience) (do i have|on my resume|did i list))\b", msg_clean)
            or re.search(r"\b(do i know|did i use|have i used|is .+ on my resume|my background|from my resume)\b", msg_clean)
            or (("resume" in msg_clean or "skills" in msg_clean or "project" in msg_clean) and "?" in msg_clean)
        ):
            return "PROFILE_QUERY"

        # General Greetings / Closings
        if re.match(r"^(hi|hello|hey|good (morning|afternoon|evening)|thanks|thank you|sounds good|okay|sure)\b", msg_clean) and len(msg_clean.split()) <= 4:
            return "GENERAL_CONVERSATION"

        # Default is Technical Answer / System Design explanation
        return "TECHNICAL_ANSWER"


class ProfileInquiryAgent:
    """
    Specialized agent to answer queries specifically about the candidate's
    extracted JSON memory (skills, projects, name, contact, highlights).
    """
    @staticmethod
    def answer(message: str, candidate_memory: CandidateProfile) -> str:
        msg_clean = message.strip().lower()

        # Name inquiry
        if re.search(r"\b(my name|who am i)\b", msg_clean):
            return f"According to your resume, your name is {candidate_memory.candidate_name}, and your primary title is {candidate_memory.title}."

        # Skills inquiry
        if re.search(r"\b(skills|technologies|tech stack)\b", msg_clean):
            skills_list = ", ".join(candidate_memory.skills) if candidate_memory.skills else "Software Engineering"
            return f"Your resume highlights the following key technical skills and technologies: {skills_list}."

        # Specific skill lookup (e.g. "Do I know Kafka?")
        for skill in candidate_memory.skills:
            if re.search(r"\b" + re.escape(skill.lower()) + r"\b", msg_clean):
                return (
                    f"Yes! Your resume confirms experience with **{skill}**. "
                    f"You have used {skill} in your technical projects. Let's delve into how you applied {skill} in your system architecture!"
                )

        # Projects inquiry
        if re.search(r"\b(projects?|work)\b", msg_clean):
            if candidate_memory.projects:
                proj_summaries = []
                for p in candidate_memory.projects:
                    techs = f" (using {', '.join(p.technologies)})" if p.technologies else ""
                    metric = f" - achieving {p.metrics}" if p.metrics else ""
                    proj_summaries.append(f"• **{p.name}**{techs}{metric}")
                return "Here are the key projects detailed on your resume:\n" + "\n".join(proj_summaries)
            else:
                return f"Your resume lists engineering experience in {candidate_memory.title}. Which project would you like to discuss in detail?"

        # Contact inquiry
        if re.search(r"\b(email|contact)\b", msg_clean):
            email_info = candidate_memory.email or "Not listed on the resume"
            return f"Your contact email from the resume is {email_info}."

        # General resume fallback
        skills_preview = ", ".join(candidate_memory.skills[:5])
        return (
            f"Based on your profile as a {candidate_memory.title}, your resume highlights skills in {skills_preview}. "
            f"Let's focus on your architectural experience. Which technical system would you like to walk through?"
        )


class MetaQueryAgent:
    """
    Specialized agent answering interview metadata inquiries (remaining time, repeating questions).
    """
    @staticmethod
    def answer(
        message: str,
        remaining_seconds: int,
        conversation_history: List[MessageItem]
    ) -> str:
        msg_clean = message.strip().lower()

        if re.search(r"\b(time|duration)\b", msg_clean):
            mins = remaining_seconds // 60
            secs = remaining_seconds % 60
            return (
                f"You have approximately **{mins:02d}:{secs:02d}** remaining in this 5-minute technical simulation. "
                "Whenever you're ready, let's continue with your technical explanation."
            )

        if re.search(r"\b(repeat|what was)\b", msg_clean):
            last_interviewer_msg = next((m for m in reversed(conversation_history) if m.role == "interviewer"), None)
            if last_interviewer_msg:
                return f"Certainly! Here is my previous question:\n\n\"{last_interviewer_msg.content}\""

        return "We are in the middle of our 5-minute technical assessment. Let's continue with your project architecture!"


class TechnicalInterviewerAgent:
    """
    Specialized technical interviewer driving system design deep-dives,
    tradeoff evaluations, bottleneck analysis, and scaling scenarios based on Candidate JSON Memory.
    """
    @staticmethod
    def evaluate_and_ask(
        candidate_memory: CandidateProfile,
        conversation_history: List[MessageItem],
        candidate_message: str
    ) -> str:
        candidate_turns = sum(1 for m in conversation_history if m.role == "candidate")

        # Pick primary project from memory if available
        primary_proj = candidate_memory.projects[0] if candidate_memory.projects else None
        proj_name = primary_proj.name if primary_proj else "your primary system"
        tech_context = f" involving {', '.join(primary_proj.technologies[:3])}" if (primary_proj and primary_proj.technologies) else ""

        if candidate_turns == 1:
            candidate_memory.topics_covered.append("System Architecture & Protocols")
            return (
                f"That's a solid architectural overview for {proj_name}{tech_context}. "
                "What were the most challenging bottlenecks or latency constraints you encountered, "
                "and how did you choose your data storage and communication protocols?"
            )
        elif candidate_turns == 2:
            candidate_memory.topics_covered.append("Scalability & Bottlenecks")
            candidate_memory.evaluated_strengths.append("Performance Optimization")
            return (
                f"Interesting engineering tradeoffs. If your {proj_name} experienced a sudden 10x traffic spike "
                "or high write contention, where would the system fail first, and what mitigation strategies (e.g., caching, sharding, backpressure) would you apply?"
            )
        elif candidate_turns == 3:
            candidate_memory.topics_covered.append("Fault Tolerance & Consistency")
            return (
                "Great analysis. How did you ensure fault tolerance, error recovery, and data consistency "
                "across distributed worker services during network partitions or database outages?"
            )
        elif candidate_turns == 4:
            candidate_memory.topics_covered.append("Retrospective & Design Decisions")
            return (
                f"Looking back at your implementation of {proj_name}, if you had the opportunity to rebuild it "
                "from scratch with modern tooling today, what architectural decision would you change and why?"
            )
        else:
            return (
                "Thank you for walking me through those details thoroughly. You have clearly articulated the architecture, "
                "tradeoffs, and engineering considerations. Do you have any specific technical questions for me about the system design or role?"
            )


class AgentOrchestrator:
    """
    Central orchestrator coordinating intent classification, memory injection,
    and agent delegation.
    """
    def __init__(self):
        self.classifier = IntentClassifier()
        self.profile_agent = ProfileInquiryAgent()
        self.meta_agent = MetaQueryAgent()
        self.tech_agent = TechnicalInterviewerAgent()

    def process_message(
        self,
        session_id: str,
        candidate_memory: CandidateProfile,
        conversation_history: List[MessageItem],
        candidate_message: str,
        remaining_seconds: int = 300
    ) -> Tuple[str, IntentType, str]:
        """
        Routes the candidate's input to the specialized agent and updates memory.
        Returns: (response_text, intent_classified, agent_used)
        """
        intent = self.classifier.classify(candidate_message)

        if intent == "PROFILE_QUERY":
            agent_used = "ProfileInquiryAgent"
            response_text = self.profile_agent.answer(candidate_message, candidate_memory)

        elif intent == "INTERVIEW_META_QUERY":
            agent_used = "MetaQueryAgent"
            response_text = self.meta_agent.answer(candidate_message, remaining_seconds, conversation_history)

        elif intent == "GENERAL_CONVERSATION":
            agent_used = "GeneralConversationalAgent"
            response_text = (
                f"Hello {candidate_memory.candidate_name.split()[0]}! Let's dive right into your technical experience. "
                f"Tell me about the design of {candidate_memory.projects[0].name if candidate_memory.projects else 'your recent project'}."
            )

        else:  # TECHNICAL_ANSWER
            agent_used = "TechnicalInterviewerAgent"
            response_text = self.tech_agent.evaluate_and_ask(
                candidate_memory,
                conversation_history,
                candidate_message
            )

        return response_text, intent, agent_used

agent_orchestrator = AgentOrchestrator()
