// Firebase Configuration for Ace Chasers
// Uses lightweight fetch-based approach to minimize bundle size

const FIREBASE_CONFIG = {
  apiKey: process.env.REACT_APP_FIREBASE_API_KEY || 'YOUR_API_KEY',
  projectId: process.env.REACT_APP_FIREBASE_PROJECT_ID || 'your-project-id',
  storageBucket: process.env.REACT_APP_FIREBASE_STORAGE_BUCKET || 'your-project.appspot.com',
  authDomain: process.env.REACT_APP_FIREBASE_AUTH_DOMAIN || 'your-project.firebaseapp.com',
};

/**
 * Upload profile picture to Firebase Storage
 * @param {File} file - The image file to upload
 * @param {string} userId - The user ID for organizing files
 * @returns {Promise<string>} - The download URL of the uploaded image
 */
export const uploadProfilePicture = async (file, userId) => {
  try {
    // Validate file
    if (!file || !file.type.startsWith('image/')) {
      throw new Error('Please select a valid image file');
    }

    if (file.size > 5 * 1024 * 1024) {
      throw new Error('File size must be less than 5MB');
    }

    // Create FormData for multipart upload
    const formData = new FormData();
    formData.append('file', file);

    // Firebase Storage REST API endpoint
    const storagePath = `${FIREBASE_CONFIG.projectId}/profilePictures/${userId}/${Date.now()}_${file.name}`;
    const uploadUrl = `https://firebaseupload.googleapis.com/upload/storage/v1/b/${FIREBASE_CONFIG.storageBucket}/o?uploadType=media&name=${encodeURIComponent(storagePath)}&key=${FIREBASE_CONFIG.apiKey}`;

    const response = await fetch(uploadUrl, {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${await getFirebaseToken()}`,
      },
      body: file,
    });

    if (!response.ok) {
      throw new Error(`Upload failed: ${response.statusText}`);
    }

    const data = await response.json();

    // Generate download URL
    const downloadUrl = `https://firebasestorage.googleapis.com/v0/b/${FIREBASE_CONFIG.storageBucket}/o/${encodeURIComponent(storagePath)}?alt=media`;

    return downloadUrl;
  } catch (error) {
    console.error('Profile picture upload error:', error);
    throw error;
  }
};

/**
 * Delete profile picture from Firebase Storage
 * @param {string} fileUrl - The download URL of the file to delete
 * @returns {Promise<boolean>} - Success status
 */
export const deleteProfilePicture = async (fileUrl) => {
  try {
    // Extract storage path from URL
    const storagePath = new URL(fileUrl).searchParams.get('name');
    
    if (!storagePath) {
      throw new Error('Invalid file URL');
    }

    const deleteUrl = `https://firebasestorage.googleapis.com/v0/b/${FIREBASE_CONFIG.storageBucket}/o/${encodeURIComponent(storagePath)}?key=${FIREBASE_CONFIG.apiKey}`;

    const response = await fetch(deleteUrl, {
      method: 'DELETE',
      headers: {
        'Authorization': `Bearer ${await getFirebaseToken()}`,
      },
    });

    return response.ok;
  } catch (error) {
    console.error('Profile picture deletion error:', error);
    throw error;
  }
};

/**
 * Get Firebase authentication token (for client-side operations)
 * Uses stored auth token or generates a new one
 * @returns {Promise<string>} - Firebase auth token
 */
export const getFirebaseToken = async () => {
  const storedToken = localStorage.getItem('firebaseAuthToken');
  const tokenExpiry = localStorage.getItem('firebaseTokenExpiry');

  // Return token if it exists and hasn't expired
  if (storedToken && tokenExpiry && Date.now() < parseInt(tokenExpiry)) {
    return storedToken;
  }

  // Generate new token (simplified - in production, use Firebase SDK)
  try {
    // This is a placeholder - implement actual Firebase auth
    const token = storedToken || 'placeholder-token';
    localStorage.setItem('firebaseAuthToken', token);
    localStorage.setItem('firebaseTokenExpiry', Date.now() + 3600000); // 1 hour

    return token;
  } catch (error) {
    console.error('Failed to get Firebase token:', error);
    throw error;
  }
};

/**
 * Get download URL for a stored profile picture
 * @param {string} userId - The user ID
 * @param {string} fileName - The file name
 * @returns {string} - The download URL
 */
export const getProfilePictureUrl = (userId, fileName) => {
  const storagePath = `${FIREBASE_CONFIG.projectId}/profilePictures/${userId}/${fileName}`;
  return `https://firebasestorage.googleapis.com/v0/b/${FIREBASE_CONFIG.storageBucket}/o/${encodeURIComponent(storagePath)}?alt=media`;
};

export default FIREBASE_CONFIG;