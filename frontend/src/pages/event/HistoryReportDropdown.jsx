import { useEffect, useId, useRef, useState } from "react";
import { CalendarDays, ChevronDown } from "lucide-react";
import HistoryReportCalendar from "./HistoryReportCalendar.jsx";
import "./historyReportDropdown.css";

export default function HistoryReportDropdown({ event }) {
  const [open, setOpen] = useState(false);
  const panelId = useId();
  const rootRef = useRef(null);
  const triggerRef = useRef(null);

  useEffect(() => {
    if (!open) return;
    function closeOutside(event) {
      if (!rootRef.current?.contains(event.target)) setOpen(false);
    }
    function closeOnEscape(event) {
      if (event.key !== "Escape") return;
      event.preventDefault();
      setOpen(false);
      triggerRef.current?.focus();
    }
    document.addEventListener("pointerdown", closeOutside);
    document.addEventListener("focusin", closeOutside);
    document.addEventListener("keydown", closeOnEscape);
    return () => {
      document.removeEventListener("pointerdown", closeOutside);
      document.removeEventListener("focusin", closeOutside);
      document.removeEventListener("keydown", closeOnEscape);
    };
  }, [open]);

  function closeAfterSelection() {
    setOpen(false);
    triggerRef.current?.focus();
  }

  return (
    <div className="dt-history-dropdown" ref={rootRef}>
      <button
        type="button"
        className="wp-button dt-history-trigger"
        ref={triggerRef}
        aria-expanded={open}
        aria-controls={panelId}
        onClick={() => setOpen((value) => !value)}
      >
        <CalendarDays size={16} aria-hidden="true" />
        날짜별 기록
        <ChevronDown size={14} aria-hidden="true" />
      </button>
      <div id={panelId} className="dt-history-popover" hidden={!open}>
        <HistoryReportCalendar event={event} onSelect={closeAfterSelection} />
      </div>
    </div>
  );
}
