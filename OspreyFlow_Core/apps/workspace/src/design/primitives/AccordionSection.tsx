import { useId, type ReactNode } from "react";

export interface AccordionSectionProps {
  title: string;
  open: boolean;
  onToggle: () => void;
  children: ReactNode;
}

/** One part of a side panel that folds away (ADR-096), drawn minimalist and bordered
 * (`primitives.css`'s `.accordion-section`): a header button that says whether it is open
 * (`aria-expanded`) and the content it controls. A folded part stays in the page, hidden, so what
 * is half-written in it is kept and nothing is fetched again on opening it. */
export function AccordionSection({ title, open, onToggle, children }: AccordionSectionProps) {
  const contentId = useId();
  return (
    <div className="accordion-section">
      <h3 className="accordion-section__heading">
        <button
          type="button"
          className="accordion-section__header"
          aria-expanded={open}
          aria-controls={contentId}
          onClick={onToggle}
        >
          <svg aria-hidden="true" className="accordion-section__chevron" viewBox="0 0 12 12" width="12" height="12">
            <path d="M4.5 2.5 8 6l-3.5 3.5" fill="none" stroke="currentColor" strokeWidth="1.5" />
          </svg>
          {title}
        </button>
      </h3>
      <div id={contentId} className="accordion-section__content" hidden={!open}>
        {children}
      </div>
    </div>
  );
}
