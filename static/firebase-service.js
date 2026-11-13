/**
 * ExamMatrix IT - Centralized Firebase & Cloud Firestore Service
 * Connects Google Authentication and Cloud Firestore.
 * Eliminates all localStorage dependency for user profiles, exam drafts, and attempts.
 */

const firebaseConfig = {
  apiKey: "AIzaSyCBfi-nwj0g6ks_I5bQYUe3ogKiDWjnORY",
  authDomain: "my-mock-app-3fc00.firebaseapp.com",
  projectId: "my-mock-app-3fc00",
  storageBucket: "my-mock-app-3fc00.firebasestorage.app",
  messagingSenderId: "75566869830",
  appId: "1:75566869830:web:4c74c29bb09a4b57430947"
};

// Initialize Firebase if not already initialized
if (typeof firebase !== 'undefined' && !firebase.apps.length) {
  firebase.initializeApp(firebaseConfig);
}

const fbAuth = typeof firebase !== 'undefined' ? firebase.auth() : null;
const fbDb = typeof firebase !== 'undefined' ? firebase.firestore() : null;

// Fruity Pseudonym Generator Pool
const FRUITY_ADJECTIVES = [
  "Velvet", "Crisp", "Golden", "Cosmic", "Zesty", "Frosty", "Electric", "Sunlit",
  "Ruby", "Emerald", "Midnight", "Breezy", "Sparkling", "Neon", "Gentle", "Swift",
  "Solar", "Luminous", "Wild", "Mystic", "Crimson", "Radiant", "Glacial", "Vibrant"
];

const FRUITS = [
  { name: "Mango", emoji: "🥭", color: "#f59e0b" },
  { name: "Kiwi", emoji: "🥝", color: "#10b981" },
  { name: "Guava", emoji: "🍈", color: "#84cc16" },
  { name: "Papaya", emoji: "🍉", color: "#f97316" },
  { name: "Tangerine", emoji: "🍊", color: "#fb923c" },
  { name: "Dragonfruit", emoji: "🐲", color: "#ec4899" },
  { name: "Apricot", emoji: "🍑", color: "#f472b6" },
  { name: "Lychee", emoji: "🍓", color: "#f43f5e" },
  { name: "Fig", emoji: "🫐", color: "#8b5cf6" },
  { name: "Kumquat", emoji: "🍋", color: "#eab308" },
  { name: "Pineapple", emoji: "🍍", color: "#eab308" },
  { name: "Plum", emoji: "🍇", color: "#a855f7" },
  { name: "Melon", emoji: "🍈", color: "#22c55e" },
  { name: "Cherry", emoji: "🍒", color: "#ef4444" },
  { name: "Passionfruit", emoji: "🥭", color: "#d946ef" },
  { name: "Coconut", emoji: "🥥", color: "#06b6d4" }
];

function generateClientFruityIdentity() {
  const adj = FRUITY_ADJECTIVES[Math.floor(Math.random() * FRUITY_ADJECTIVES.length)];
  const fruit = FRUITS[Math.floor(Math.random() * FRUITS.length)];
  const num = Math.floor(Math.random() * 900) + 100;
  const username = `${adj} ${fruit.name} #${num}`;
  const handle = `@${adj.toLowerCase()}_${fruit.name.toLowerCase()}_${num}`;
  return { username, handle, fruitEmoji: fruit.emoji, avatarColor: fruit.color };
}

/**
 * Sign In with Google via Firebase OAuth Popup
 */
async function firebaseGoogleSignIn() {
  if (!fbAuth) throw new Error("Firebase Auth is not available.");
  const provider = new firebase.auth.GoogleAuthProvider();
  provider.setCustomParameters({ prompt: 'select_account' });
  const result = await fbAuth.signInWithPopup(provider);
  return await getOrCreateFirestoreUser(result.user);
}

/**
 * Sign Out User
 */
async function firebaseSignOut() {
  if (!fbAuth) return;
  await fbAuth.signOut();
  // Also clear Flask server session if present
  try { await fetch('/api/auth/logout', { method: 'POST' }); } catch (e) {}
}

/**
 * Retrieve or generate permanent Anonymous Fruity Profile in Firestore
 * Stored in `users/{uid}`. Email is NEVER shown publicly.
 */
async function getOrCreateFirestoreUser(user) {
  if (!user || !fbDb) return null;
  const userRef = fbDb.collection('users').doc(user.uid);
  try {
    const doc = await userRef.get();
    if (doc.exists) {
      const data = doc.data();
      userRef.update({ lastLogin: firebase.firestore.FieldValue.serverTimestamp() }).catch(() => {});
      return {
        uid: user.uid,
        username: data.username,
        handle: data.handle,
        fruitEmoji: data.fruitEmoji || '🥭',
        avatarColor: data.avatarColor || '#34d399',
        isAdmin: Boolean(data.isAdmin),
        createdAt: data.createdAt ? (data.createdAt.toDate ? data.createdAt.toDate().toISOString() : null) : null
      };
    }

    // New User: Assign unique Fruity identity
    const identity = generateClientFruityIdentity();
    const newProfile = {
      uid: user.uid,
      email: user.email || '', // strictly private / admin record
      username: identity.username,
      handle: identity.handle,
      fruitEmoji: identity.fruitEmoji,
      avatarColor: identity.avatarColor,
      isAdmin: (user.email && user.email.toLowerCase().includes('admin')),
      createdAt: firebase.firestore.FieldValue.serverTimestamp(),
      lastLogin: firebase.firestore.FieldValue.serverTimestamp()
    };
    await userRef.set(newProfile);

    // Sync session with Flask backend if available
    try {
      await fetch('/api/auth/demo-login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ role: 'candidate', candidateId: user.uid.slice(0, 8) })
      });
    } catch (e) {}

    return {
      uid: user.uid,
      username: newProfile.username,
      handle: newProfile.handle,
      fruitEmoji: newProfile.fruitEmoji,
      avatarColor: newProfile.avatarColor,
      isAdmin: newProfile.isAdmin,
      createdAt: new Date().toISOString()
    };
  } catch (err) {
    console.warn("Firestore user sync error:", err);
    const fallback = generateClientFruityIdentity();
    return {
      uid: user.uid,
      username: fallback.username,
      handle: fallback.handle,
      fruitEmoji: fallback.fruitEmoji,
      avatarColor: fallback.avatarColor,
      isAdmin: false
    };
  }
}

/**
 * Auth State Listener
 */
function onFirebaseAuthChange(callback) {
  if (!fbAuth) return () => {};
  return fbAuth.onAuthStateChanged(async (user) => {
    if (user) {
      const profile = await getOrCreateFirestoreUser(user);
      callback(profile);
    } else {
      callback(null);
    }
  });
}

/**
 * Safely resolves active Firebase user, checking parent iframe context and auth state
 */
async function getActiveUser() {
  if (fbAuth && fbAuth.currentUser) return fbAuth.currentUser;
  try {
    if (typeof window !== 'undefined' && window.parent && window.parent !== window && window.parent.fbAuth && window.parent.fbAuth.currentUser) {
      return window.parent.fbAuth.currentUser;
    }
  } catch (e) {}

  if (fbAuth) {
    return new Promise(resolve => {
      const unsub = fbAuth.onAuthStateChanged(u => {
        unsub();
        resolve(u);
      });
      setTimeout(() => resolve(fbAuth ? fbAuth.currentUser : null), 800);
    });
  }
  return null;
}

/**
 * Save Completed Mock Exam Attempt into Cloud Firestore
 * Replaces localStorage quiz_result_*
 */
async function saveAttemptToFirestore(attempt) {
  if (!fbDb) return null;
  const user = await getActiveUser();
  const parentUser = (typeof window !== 'undefined' && window.parent && window.parent.globalUser) ? window.parent.globalUser : null;
  const uid = user ? user.uid : (parentUser ? parentUser.uid : (attempt.userId || 'anonymous_guest'));

  let username = (parentUser && parentUser.username) ? parentUser.username : 'Candidate';
  let handle = (parentUser && parentUser.handle) ? parentUser.handle : '@candidate';
  let emoji = (parentUser && parentUser.fruitEmoji) ? parentUser.fruitEmoji : '🥭';

  if (user && fbDb) {
    try {
      const uDoc = await fbDb.collection('users').doc(user.uid).get();
      if (uDoc.exists) {
        const uData = uDoc.data();
        username = uData.username || username;
        handle = uData.handle || handle;
        emoji = uData.fruitEmoji || emoji;
      }
    } catch (e) {}
  }

  const qDay = Number(attempt.quizDay) || 0;
  const defTitle = qDay > 0 ? `IT Officer Mains: Day ${qDay}` : 'Custom Assessment';

  const payload = {
    userId: uid,
    username: username,
    userHandle: handle,
    userFruitEmoji: emoji,
    examId: String(attempt.examId || (qDay > 0 ? `day_${qDay}` : 'custom')),
    quizDay: qDay,
    quizTitle: attempt.quizTitle || defTitle,
    score: Number(attempt.score) || 0,
    correct: Number(attempt.correct) || 0,
    incorrect: Number(attempt.incorrect) || 0,
    unattempted: Number(attempt.unattempted) || 0,
    totalQuestions: Number(attempt.totalQuestions) || 50,
    accuracy: Number(attempt.accuracy) || 0,
    timeTakenSeconds: Number(attempt.timeTakenSeconds) || 0,
    topicBreakdown: attempt.topicBreakdown || {},
    date: firebase.firestore.FieldValue.serverTimestamp()
  };

  try {
    const docRef = await fbDb.collection('attempts').add(payload);
    return { id: docRef.id, ...payload, date: new Date().toISOString() };
  } catch (err) {
    console.error("Firestore save attempt error:", err);
    return null;
  }
}

/**
 * Real-Time Firestore Attempt Subscription
 * Streams all user attempts live without needing localStorage
 */
function subscribeFirestoreAttempts(uid, onUpdate) {
  if (!fbDb || !uid) return () => {};
  return fbDb.collection('attempts')
    .where('userId', '==', uid)
    .onSnapshot((snapshot) => {
      const attempts = [];
      snapshot.forEach(doc => {
        const d = doc.data();
        attempts.push({
          id: doc.id,
          ...d,
          date: d.date ? (d.date.toDate ? d.date.toDate().toISOString() : d.date) : new Date().toISOString()
        });
      });
      attempts.sort((a, b) => new Date(a.date || 0) - new Date(b.date || 0));
      onUpdate(attempts);
    }, (error) => {
      console.warn("Firestore subscription error:", error);
    });
}

/**
 * Cloud Exam Draft Autosave (Replaces localStorage exam draft)
 */
async function saveCloudDraft(quizId, draftState) {
  if (!fbDb || !fbAuth || !fbAuth.currentUser) return;
  const uid = fbAuth.currentUser.uid;
  const cleanId = String(quizId).replace(/[^a-zA-Z0-9_]/g, '');
  try {
    await fbDb.collection('users').doc(uid).collection('active_drafts').doc(cleanId).set({
      ...draftState,
      lastSaved: firebase.firestore.FieldValue.serverTimestamp()
    }, { merge: true });
  } catch (e) {
    console.warn("Could not save cloud draft:", e);
  }
}

/**
 * Retrieve Cloud Exam Draft
 */
async function getCloudDraft(quizId) {
  if (!fbDb || !fbAuth || !fbAuth.currentUser) return null;
  const uid = fbAuth.currentUser.uid;
  const cleanId = String(quizId).replace(/[^a-zA-Z0-9_]/g, '');
  try {
    const doc = await fbDb.collection('users').doc(uid).collection('active_drafts').doc(cleanId).get();
    return doc.exists ? doc.data() : null;
  } catch (e) {
    return null;
  }
}

/**
 * Clear Cloud Exam Draft
 */
async function clearCloudDraft(quizId) {
  if (!fbDb || !fbAuth || !fbAuth.currentUser) return;
  const uid = fbAuth.currentUser.uid;
  const cleanId = String(quizId).replace(/[^a-zA-Z0-9_]/g, '');
  try {
    await fbDb.collection('users').doc(uid).collection('active_drafts').doc(cleanId).delete();
  } catch (e) {}
}

/**
 * Wipe all user attempts from Cloud Firestore (Replaces resetAllProgress localStorage purge)
 */
async function clearUserAttemptsFromFirestore(uid) {
  if (!fbDb || !uid) return;
  try {
    const snapshot = await fbDb.collection('attempts').where('userId', '==', uid).get();
    const batch = fbDb.batch();
    snapshot.forEach(doc => batch.delete(doc.ref));
    await batch.commit();
  } catch (e) {
    console.error("Error wiping Firestore attempts:", e);
  }
}
