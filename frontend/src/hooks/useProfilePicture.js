import { useState } from 'react';
import { uploadProfilePicture, deleteProfilePicture } from '../config/firebase';

/**
 * Custom hook for managing profile picture uploads
 * Handles file selection, validation, and Firebase upload
 */
export const useProfilePicture = () => {
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState(null);
  const [imageUrl, setImageUrl] = useState(null);

  /**
   * Handle file selection and upload
   * @param {File} file - The selected image file
   * @param {string} userId - The user ID
   */
  const handleFileUpload = async (file, userId) => {
    setError(null);
    setUploading(true);

    try {
      // Delete old image if exists
      if (imageUrl) {
        await deleteProfilePicture(imageUrl).catch((err) => {
          console.warn('Failed to delete old image:', err);
        });
      }

      // Upload new image
      const url = await uploadProfilePicture(file, userId);
      setImageUrl(url);
      return url;
    } catch (err) {
      const errorMessage = err.message || 'Failed to upload profile picture';
      setError(errorMessage);
      throw err;
    } finally {
      setUploading(false);
    }
  };

  /**
   * Clear the current image
   */
  const clearImage = () => {
    setImageUrl(null);
    setError(null);
  };

  return {
    imageUrl,
    uploading,
    error,
    handleFileUpload,
    clearImage,
  };
};

export default useProfilePicture;