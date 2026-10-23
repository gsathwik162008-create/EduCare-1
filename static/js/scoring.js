/**
 * Smart Campus Analytics - Scoring Logic (JS)
 * STRICT PARITY with Python implementation in app/scoring.py
 */

export function computeIndicatorScores(metrics, year = 3){
    // 1. Academic Score (0-100)
    const cgpa = Math.max(0.0, Math.min(10.0, parseFloat(metrics.cgpa || 0.0)));
    const backlogs = Math.max(0, parseInt(metrics.total_backlogs || 0, 10));
    const academic_score = Math.max(0.0, Math.min(100.0, (cgpa * 10.0) - (backlogs * 10.0)));

    // 2. Attendance Score (0-100)
    const attendance_score = Math.max(0.0, Math.min(100.0, parseFloat(metrics.attendance_pct || 0.0)));

    // 3. Placement Readiness Score (0-100)
    const apt = Math.max(0.0, Math.min(100.0, parseFloat(metrics.aptitude_score || 0.0)));
    const code = Math.max(0.0, Math.min(100.0, parseFloat(metrics.coding_score || 0.0)));
    const mocks = Math.max(0, parseInt(metrics.mock_interviews_completed || 0, 10));
    const mock_score = Math.min(100.0, mocks * 50.0);
    const placement_score = year >= 3
        ? Math.round((0.35 * apt + 0.45 * code + 0.20 * mock_score) * 100) / 100
        : Math.round(((0.35 * apt + 0.45 * code) / 0.80) * 100) / 100;
    // 4. LMS & Engagement Score (0-100)
    const assign_pct = Math.max(0.0, Math.min(100.0, parseFloat(metrics.assignments_submitted_pct || 0.0)));
    const logins = Math.max(0, parseInt(metrics.lms_login_count || 0, 10));
    const login_score = Math.min(100.0, (logins / 150.0) * 100.0);
    const forum_posts = Math.max(0, parseInt(metrics.forum_posts_count || 0, 10));
    const events = Math.max(0, parseInt(metrics.event_participation_count || 0, 10));
    const engagement_extra = Math.min(100.0, (forum_posts * 10.0) + (events * 15.0));
    const lms_score = Math.round((0.50 * assign_pct + 0.30 * login_score + 0.20 * engagement_extra) * 100) / 100;

    // 5. Skills & Feedback Score (0-100)
    const tech = Math.max(0.0, Math.min(100.0, parseFloat(metrics.technical_skills_score || 0.0)));
    const soft = Math.max(0.0, Math.min(100.0, parseFloat(metrics.soft_skills_score || 0.0)));
    const fac_fb = Math.max(0.0, Math.min(100.0, parseFloat(metrics.faculty_feedback_score || 0.0)));
    const peer_fb = Math.max(0.0, Math.min(100.0, parseFloat(metrics.peer_feedback_score || 0.0)));
    const skills_score = Math.round((0.35 * tech + 0.25 * soft + 0.20 * fac_fb + 0.20 * peer_fb) * 100) / 100;

    return {
        academic_score: Math.round(academic_score * 100) / 100,
        attendance_score: Math.round(attendance_score * 100) / 100,
        placement_score: placement_score,
        lms_score: lms_score,
        skills_feedback_score: skills_score
    };
}

export function computeSuccessScore(subScores, weights = {}) {
    const w_acad = weights.weight_academic !== undefined ? weights.weight_academic : 35.0;
    const w_att = weights.weight_attendance !== undefined ? weights.weight_attendance : 20.0;
    const w_place = weights.weight_placement !== undefined ? weights.weight_placement : 20.0;
    const w_lms = weights.weight_lms !== undefined ? weights.weight_lms : 15.0;
    const w_skills = weights.weight_skills !== undefined ? weights.weight_skills : 10.0;

    let total_weight = w_acad + w_att + w_place + w_lms + w_skills;
    if (total_weight <= 0) total_weight = 100.0;

    const raw_sum = (
        subScores.academic_score * w_acad +
        subScores.attendance_score * w_att +
        subScores.placement_score * w_place +
        subScores.lms_score * w_lms +
        subScores.skills_feedback_score * w_skills
    );

    const score = Math.max(0.0, Math.min(100.0, raw_sum / total_weight));
    return Math.round(score * 100) / 100;
}

export function evaluateRisks(metrics, year = 3) {
    const cgpa = parseFloat(metrics.cgpa || 0);
    const backlogs = parseInt(metrics.total_backlogs || 0, 10);
    const att = parseFloat(metrics.attendance_pct || 0);
    const code = parseFloat(metrics.coding_score || 0);
    const apt = parseFloat(metrics.aptitude_score || 0);
    const mocks = parseInt(metrics.mock_interviews_completed || 0, 10);
    const tech = parseFloat(metrics.technical_skills_score || 0);

    // Academic Risk
    const acadReasons = [];
    if (cgpa < 5.0) acadReasons.push(`Critical CGPA ${cgpa.toFixed(2)} (< 5.0)`);
    else if (cgpa < 6.0) acadReasons.push(`CGPA ${cgpa.toFixed(2)} below threshold 6.0`);

    if (att < 65.0) acadReasons.push(`Critical attendance ${att.toFixed(1)}% (< 65%)`);
    else if (att < 75.0) acadReasons.push(`Attendance ${att.toFixed(1)}% below required 75%`);

    if (backlogs >= 2) acadReasons.push(`Multiple active backlogs (${backlogs})`);
    else if (backlogs === 1) acadReasons.push("1 active backlog pending clearance");

    let acadLevel = "Low";
    if (cgpa < 5.0 || att < 65.0 || backlogs >= 2) {
        acadLevel = "High";
    } else if (cgpa < 6.0 || att < 75.0 || backlogs === 1) {
        acadLevel = "Medium";
    }

    // Placement Risk
    const placeReasons = [];
    if (code < 40.0) placeReasons.push(`Coding score ${code.toFixed(1)} below hiring cutoff (needs 40)`);
    if (apt < 50.0) placeReasons.push(`Aptitude benchmark missed (${apt.toFixed(1)} < 50)`);
    if (year >= 3 && mocks === 0) placeReasons.push(`No mock interviews completed in Year ${year}`);
    if (tech < 50.0) placeReasons.push(`Technical domain skills low (${tech.toFixed(1)})`);

    let placeLevel = "Low";
    if (code < 35.0 || (year >= 3 && mocks === 0 && code < 45.0)) {
        placeLevel = "High";
    } else if (code < 40.0 || apt < 50.0 || (year >= 3 && mocks === 0) || tech < 50.0) {
        placeLevel = "Medium";
    }

    return {
        academic_risk_level: acadLevel,
        academic_risk_reasons: acadReasons,
        placement_risk_level: placeLevel,
        placement_risk_reasons: placeReasons
    };
}

export function evaluateWhatIf(baseMetrics, adjustments, weights = {}, year = 3) {
    const simMetrics = { ...baseMetrics };
    
    // Apply slider adjustments
    for (const [k, v] of Object.entries(adjustments)) {
        simMetrics[k] = parseFloat(v);
    }

    const baseSub = computeIndicatorScores(baseMetrics);
    const baseScore = computeSuccessScore(baseSub, weights);

    const simSub = computeIndicatorScores(simMetrics);
    const simScore = computeSuccessScore(simSub, weights);
    const risks = evaluateRisks(simMetrics, year);

    // Identify biggest lever
    // Test a +10 point bump or +1 unit for each controllable dimension
    const candidates = [
        { key: "attendance_pct", label: "Attendance (+10%)", delta: 10, current: simMetrics.attendance_pct || 70, max: 100 },
        { key: "coding_score", label: "Coding Practice (+15 pts)", delta: 15, current: simMetrics.coding_score || 50, max: 100 },
        { key: "mock_interviews_completed", label: "Mock Interviews (+1 session)", delta: 1, current: simMetrics.mock_interviews_completed || 0, max: 4 },
        { key: "assignments_submitted_pct", label: "Assignment Completion (+10%)", delta: 10, current: simMetrics.assignments_submitted_pct || 75, max: 100 },
        { key: "technical_skills_score", label: "Technical Certifications (+10 pts)", delta: 10, current: simMetrics.technical_skills_score || 60, max: 100 },
    ];

    let biggestLever = "Continue balanced effort";
    let maxGain = 0;

    for (const cand of candidates) {
        const testMetrics = { ...simMetrics };
        testMetrics[cand.key] = Math.min(cand.max, (parseFloat(testMetrics[cand.key] || 0) + cand.delta));
        const testSub = computeIndicatorScores(testMetrics);
        const testScore = computeSuccessScore(testSub, weights);
        const gain = testScore - simScore;
        if (gain > maxGain) {
            maxGain = gain;
            biggestLever = `${cand.label} (+${gain.toFixed(1)} score gain)`;
        }
    }

    return {
        simulatedScore: simScore,
        scoreDelta: Math.round((simScore - baseScore) * 100) / 100,
        subScores: simSub,
        risks: risks,
        biggestLever: biggestLever
    };
}
