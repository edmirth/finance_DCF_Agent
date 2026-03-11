import { ArrowRight } from 'lucide-react';

interface FollowUpQuestionsProps {
  questions: string[];
  onQuestionClick: (question: string) => void;
}

function FollowUpQuestions({ questions, onQuestionClick }: FollowUpQuestionsProps) {
  if (questions.length === 0) return null;

  return (
    <div className="fu-section">
      <div className="fu-header">Related</div>
      {questions.map((question, index) => (
        <button
          key={index}
          className="fu-item"
          onClick={() => onQuestionClick(question)}
        >
          <ArrowRight className="fu-icon" size={14} />
          <span className="fu-text">{question}</span>
        </button>
      ))}
    </div>
  );
}

export default FollowUpQuestions;
