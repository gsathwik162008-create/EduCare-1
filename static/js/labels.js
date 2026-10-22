/**
 * Smart Campus Analytics - Plain Language Labels & Guidance
 * Designed for college faculty, administrators, and students.
 * Short sentences (<15 words), everyday words, no jargon, numbers with units.
 */

export const LABELS = {
    // Core Concepts
    scoreName: "Success Score",
    scoreHelp: "A score out of 100 showing how well a student is doing overall.",
    scoreOutScores: "out of 100",
    collegeAverage: "college average",
    middleValue: "middle value",
    minimumNeeded: "minimum needed",
    linkBetween: "link between",
    filledIn: "filled in",
    uploadingData: "uploading data",

    // Attention Levels (Staff)
    attentionUrgent: "Needs attention: Urgent",
    attentionSoon: "Needs attention: Soon",
    attentionFine: "Needs attention: Doing fine",

    // Student View
    studentFocusAreas: "Focus areas",
    studentStrengths: "What you are doing well",

    // Academic & Placement
    studiesNeedSupport: "Studies need support",
    studiesHelp: "Shows if a student needs help passing courses or improving grades.",
    jobReadinessNeedsSupport: "Job readiness needs support",
    jobReadinessHelp: "Shows if a student needs help preparing for job interviews.",

    // Support Actions & Priority
    supportAction: "Support action",
    supportActions: "Support actions",
    whoToHelpFirst: "Who to help first",
    whoToHelpFirstHelp: "Students who need help quickly and have the most room to improve.",
    scoreCanImproveBy: "Score can improve by",
    scoreCanImproveByHelp: "Points the student can gain by completing this support step.",

    // Student Groups
    studentGroups: "Student groups",
    studentGroupsHelp: "Students grouped together by their study habits and campus activity.",

    // Try a Change (What-If)
    tryAChange: "Try a change",
    tryAChangeSubtitle: "See how the score changes if this student improves one thing",
    tryAChangeHelp: "Move the sliders to see how small changes boost the overall score.",

    // Drivers & Influences
    whatAffectsScore: "What affects this score the most",
    whatAffectsScoreHelp: "Shows which daily habits add to or lower this student's score.",

    // Systems & Activities
    onlinePortal: "Online learning portal",
    clubsAndActivities: "Clubs and activities",

    // Early Warning / ML Model
    earlyWarningAccuracy: "How often the early warning is right",
    earlyWarningAccuracyHelp: "Tells you how reliably the system spots students who need support early.",

    // Fixed Departments & Colors
    departments: [
        { code: "CSE", name: "Computer Science", color: "#0F5C5C" },
        { code: "ECE", name: "Electronics", color: "#2563EB" },
        { code: "EEE", name: "Electrical", color: "#6366F1" },
        { code: "Mech", name: "Mechanical", color: "#7C3AED" },
        { code: "Civil", name: "Civil", color: "#475569" }
    ],

    // Navigation Items
    nav: {
        overview: "College Overview",
        trends: "Changes Over Time",
        riskExplorer: "Students Needing Support",
        actionList: "Who to Help First",
        studentProfile: "Student Profile",
        segments: "Student Groups",
        insights: "Key Findings & Feedback",
        dataQuality: "Upload Data & Records",
        modelSettings: "Early Warning & Scoring Rules",
        scoreGuide: "How the Score Works",
        // Student Nav
        studentProgress: "My Progress",
        studentWhatIf: "Try a Change",
        studentActions: "My Next Steps",
        studentMentor: "Ask My Mentor"
    },

    // Screen Header Descriptions
    screens: {
        overview: {
            title: "College Overview",
            subtitle: "A quick view of student progress, scores, and support needs across campus."
        },
        trends: {
            title: "Changes Over Time",
            subtitle: "See whether grades, attendance, and scores are rising or falling."
        },
        riskExplorer: {
            title: "Students Needing Support",
            subtitle: "Find students who need academic or job readiness help right now."
        },
        actionList: {
            title: "Who to Help First",
            subtitle: "Recommended support actions ranked by urgency and potential score gain."
        },
        studentProfile: {
            title: "Student Profile",
            subtitle: "Personal score breakdown, course history, and steps to improve."
        },
        segments: {
            title: "Student Groups",
            subtitle: "Explore groups of students with similar study and readiness patterns."
        },
        insights: {
            title: "Key Findings & Feedback",
            subtitle: "Important patterns found in campus data and simple questions you can ask."
        },
        dataQuality: {
            title: "Upload Data & Records",
            subtitle: "Add new semester files and review automatic data checks."
        },
        modelSettings: {
            title: "Early Warning & Scoring Rules",
            subtitle: "Check early warning reliability and adjust how much each area counts."
        },
        scoreGuide: {
            title: "How the Score Works",
            subtitle: "A simple guide to the five parts that build every student's score."
        },
        studentPortal: {
            title: "Welcome to Your Progress Portal",
            subtitle: "Track your scores, discover your strengths, and see how to grow."
        }
    }
};

/**
 * Returns plain-text attention label for staff screens.
 */
export function getAttentionText(level) {
    if (!level) return LABELS.attentionFine;
    const l = String(level).toLowerCase();
    if (l === "high" || l === "urgent") return LABELS.attentionUrgent;
    if (l === "medium" || l === "soon") return LABELS.attentionSoon;
    return LABELS.attentionFine;
}

/**
 * Returns accessible colored dot + word badge for attention level.
 */
export function getAttentionBadgeHtml(level) {
    if (!level) level = "low";
    const l = String(level).toLowerCase();
    if (l === "high" || l === "urgent") {
        return `<span class="status-badge status-urgent"><span class="status-dot dot-urgent"></span>Urgent</span>`;
    }
    if (l === "medium" || l === "soon") {
        return `<span class="status-badge status-soon"><span class="status-dot dot-soon"></span>Soon</span>`;
    }
    return `<span class="status-badge status-fine"><span class="status-dot dot-fine"></span>Doing fine</span>`;
}

/**
 * Department color lookup ensuring strict consistency.
 */
export function getDepartmentColor(deptCode) {
    const found = LABELS.departments.find(d => d.code === deptCode);
    return found ? found.color : "#0F5C5C";
}

/**
 * Number formatting with proper units and rounding
 */
export function formatScore(num) {
    if (num === undefined || num === null || isNaN(num)) return "0";
    return String(Math.round(Number(num)));
}

export function formatPercent(num) {
    if (num === undefined || num === null || isNaN(num)) return "0%";
    return `${Math.round(Number(num))}%`;
}

export function formatCount(num) {
    if (num === undefined || num === null || isNaN(num)) return "0";
    return Number(num).toLocaleString();
}

export function formatGpa(num) {
    if (num === undefined || num === null || isNaN(num)) return "0.0";
    return Number(num).toFixed(1);
}

/**
 * Creates inline ? help icon that triggers an accessible tooltip/popover.
 */
export function helpTip(text) {
    const cleanText = String(text).replace(/"/g, '&quot;');
    return `<button type="button" class="help-btn" data-help="${cleanText}" title="Help" aria-label="Help: ${cleanText}">?</button>`;
}
