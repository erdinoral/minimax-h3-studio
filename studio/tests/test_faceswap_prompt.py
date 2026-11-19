import unittest

from lib.comfy import enhance_video_ref_prompt


class FaceSwapPromptTest(unittest.TestCase):
    def test_tagged_prompt_still_receives_timeline_lock(self):
        original = 'Edit <Video 1>. Replace only the man on the left using <Picture 1>.'
        result = enhance_video_ref_prompt(original, n_videos=1, role='face_swap', n_images=1)
        self.assertIn('Source timeline lock:', result)
        self.assertIn('sole edited region', result)
        self.assertIn('Preserve the source hairstyle', result)
        self.assertIn('<Picture 1> supplies facial identity only', result)
        self.assertIn('Preserve the source audio and its synchronization', result)
        for word in ('explosion', 'flames', 'smoke', 'debris'):
            self.assertNotIn(word, result.lower())
        self.assertTrue(result.endswith(original))
        self.assertEqual(enhance_video_ref_prompt(result, n_videos=1, role='face_swap', n_images=1), result)

    def test_other_motion_roles_and_missing_video_are_preserved(self):
        for role in ('motion', 'swap'):
            text = 'Use <Video 1> as described.'
            self.assertEqual(enhance_video_ref_prompt(text, n_videos=1, role=role), text)
        self.assertEqual(enhance_video_ref_prompt('Portrait', n_videos=0, role='face_swap'), 'Portrait')


if __name__ == '__main__':
    unittest.main()
