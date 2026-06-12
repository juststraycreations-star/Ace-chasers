import { useState, useRef } from 'react';
import { useProfilePicture } from '../hooks/useProfilePicture';

const ProfilePictureUpload = ({ userId, onImageUpload, currentImage }) => {
  const fileInputRef = useRef(null);
  const { imageUrl, uploading, error, handleFileUpload } = useProfilePicture();
  const [previewUrl, setPreviewUrl] = useState(currentImage || null);

  const handleFileSelect = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;

    // Create preview
    const preview = URL.createObjectURL(file);
    setPreviewUrl(preview);

    try {
      const uploadedUrl = await handleFileUpload(file, userId);
      onImageUpload?.(uploadedUrl);
    } catch (err) {
      // Reset preview on error
      setPreviewUrl(currentImage || null);
    }
  };

  const handleClick = () => {
    fileInputRef.current?.click();
  };

  return (
    <div className="relative inline-block">
      {/* Image Display */}
      <div
        className="w-32 h-32 rounded-full border-4 border-white shadow-lg cursor-pointer overflow-hidden bg-gray-200 flex items-center justify-center"
        onClick={handleClick}
      >
        {previewUrl ? (
          <img
            src={previewUrl}
            alt="Profile"
            className="w-full h-full object-cover"
          />
        ) : (
          <div className="text-center">
            <p className="text-gray-500 text-sm">Add Photo</p>
          </div>
        )}
      </div>

      {/* Upload Indicator */}
      {uploading && (
        <div className="absolute inset-0 bg-black/50 rounded-full flex items-center justify-center">
          <div className="animate-spin">
            <svg className="w-6 h-6 text-white" fill="none" viewBox="0 0 24 24">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
            </svg>
          </div>
        </div>
      )}

      {/* Hidden File Input */}
      <input
        ref={fileInputRef}
        type="file"
        accept="image/*"
        onChange={handleFileSelect}
        className="hidden"
        disabled={uploading}
      />

      {/* Error Message */}
      {error && (
        <div className="absolute top-full mt-2 text-red-600 text-sm whitespace-nowrap">
          {error}
        </div>
      )}
    </div>
  );
};

export default ProfilePictureUpload;