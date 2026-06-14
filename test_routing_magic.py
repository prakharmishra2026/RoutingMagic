import unittest
from unittest.mock import patch, mock_open, MagicMock
import os
import json
import sys

# Ensure we can import openai_wrapper properly
sys.path.append(os.path.expanduser("~/Projects/RoutingMagic"))
import openai_wrapper
from openai_wrapper import smart_route, get_client_and_model

class TestRoutingMagic(unittest.TestCase):
    # 1. Exact keyword 'math' -> nemotron-3-super-120b
    def test_smart_route_math(self):
        model, role = smart_route("Help me solve this math problem")
        self.assertEqual(model, "nvidia/nemotron-3-super-120b-a12b:free")
        self.assertEqual(role, "financial_math_reasoning")

    # 2. Phrasing 'financial analysis' -> nemotron-3-super-120b
    def test_smart_route_financial_analysis(self):
        model, role = smart_route("Can you do a financial analysis?")
        self.assertEqual(model, "nvidia/nemotron-3-super-120b-a12b:free")

    # 3. Planning 'large repo' -> nemotron-3-super-120b
    def test_smart_route_large_repo(self):
        model, role = smart_route("I have a large repo")
        self.assertEqual(model, "nvidia/nemotron-3-super-120b-a12b:free")

    # 4. Coding 'code snippet' -> qwen3-coder
    def test_smart_route_code_snippet(self):
        model, role = smart_route("Write a code snippet")
        self.assertEqual(model, "qwen/qwen3-coder:free")

    # 5. Tool 'extract data to json' -> llama-3.3-70b-instruct
    def test_smart_route_extract_json(self):
        model, role = smart_route("extract data to json")
        self.assertEqual(model, "meta-llama/llama-3.3-70b-instruct:free")

    # 6. Vision 'look at this image' -> llama-3.1-nemotron-nano-vl-8b
    def test_smart_route_vision(self):
        model, role = smart_route("look at this image")
        self.assertEqual(model, "nvidia/llama-3.1-nemotron-nano-vl-8b-v1")

    # 7. OCR 'annual report pdf' -> nemotron-ocr-v1
    def test_smart_route_ocr(self):
        model, role = smart_route("scan this annual report pdf")
        self.assertEqual(model, "nvidia/nemotron-ocr-v1")

    # 8. Voice 'voice transcription' -> nemotron-voicechat
    def test_smart_route_voice(self):
        model, role = smart_route("do a voice transcription")
        self.assertEqual(model, "nvidia/nemotron-voicechat")

    # 9. Omni 'video analysis' -> nemotron-3-nano-omni
    def test_smart_route_omni(self):
        model, role = smart_route("video analysis")
        self.assertEqual(model, "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning")

    # 10. General 'hello how are you' -> gemma-4-31b-it
    def test_smart_route_general(self):
        model, role = smart_route("hello how are you")
        self.assertEqual(model, "google/gemma-4-31b-it:free")

    # 11. Case Insensitivity
    def test_smart_route_case_insensitivity(self):
        model, role = smart_route("can you parse this PDF please?")
        self.assertEqual(model, "nvidia/nemotron-ocr-v1")
        model2, role2 = smart_route("MATH tradeoffs")
        self.assertEqual(model2, "nvidia/nemotron-3-super-120b-a12b:free")

    # 12. Context missing package.json
    @patch('openai_wrapper.os.path.exists')
    @patch('openai_wrapper.os.listdir')
    @patch('openai_wrapper.subprocess.check_output')
    def test_get_instant_context_missing_package_json(self, mock_subprocess, mock_listdir, mock_exists):
        mock_exists.side_effect = lambda x: False
        mock_listdir.return_value = ["fileA", "fileB"]
        mock_subprocess.return_value = b"status"
        res = openai_wrapper.get_instant_context()
        self.assertNotIn("README excerpt:", res)
        self.assertNotIn("package.json", res)

    # 13. Context tiny README
    @patch('openai_wrapper.os.path.exists')
    @patch('builtins.open', new_callable=mock_open, read_data="line1\\nline2")
    @patch('openai_wrapper.subprocess.check_output')
    def test_get_instant_context_tiny_readme(self, mock_subprocess, mock_open_func, mock_exists):
        mock_exists.side_effect = lambda x: 'README.md' in x
        mock_subprocess.return_value = b"status"
        res = openai_wrapper.get_instant_context()
        self.assertIn("line1", res)

    # 14. Deep Context prioritizes memory.md
    @patch('openai_wrapper.os.path.exists')
    @patch('builtins.open', new_callable=mock_open, read_data="memory content")
    @patch('openai_wrapper.subprocess.check_output')
    def test_get_deep_context_with_memory(self, mock_subprocess, mock_open_func, mock_exists):
        mock_subprocess.return_value = b""
        mock_exists.side_effect = lambda x: 'memory.md' in x
        res = openai_wrapper.get_deep_context()
        self.assertIn("memory content", res)

    # 15. Deep Context falls back to ls -R
    @patch('openai_wrapper.os.path.exists')
    @patch('openai_wrapper.get_client_and_model')
    @patch('openai_wrapper.subprocess.check_output')
    def test_get_deep_context_ls_fallback(self, mock_subprocess, mock_get_client, mock_exists):
        mock_exists.side_effect = lambda x: False
        mock_subprocess.return_value = b"file1\nfile2"
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value.choices = [MagicMock(message=MagicMock(content="Mocked summary with file1"))]
        mock_get_client.return_value = (mock_client, "model")
        res = openai_wrapper.get_deep_context()
        self.assertIn("file1", res)

    # 16. Deep context summarizer fallback
    @patch('openai_wrapper.get_client_and_model')
    @patch('openai_wrapper.get_instant_context')
    @patch('openai_wrapper.os.path.exists')
    def test_get_deep_context_summarizer_fallback(self, mock_exists, mock_gic, mock_get_client):
        mock_exists.side_effect = lambda x: False
        mock_gic.return_value = "fake hist"
        
        mock_client_fail = MagicMock()
        mock_client_fail.chat.completions.create.side_effect = Exception("API Down")
        
        mock_client_success = MagicMock()
        mock_client_success.chat.completions.create.return_value.choices = [
            MagicMock(message=MagicMock(content="summarized output"))
        ]
        
        mock_get_client.side_effect = [
            (mock_client_fail, "model1"),
            (mock_client_success, "model2")
        ]
        
        res = openai_wrapper.compress_context([{"role": "user", "content": "x"} for i in range(8)])
        self.assertEqual(res[1]["content"], "[SYSTEM: Previous context summary]\nsummarized output")

    # 17. chat_oneshot cascades on failure
    @patch('openai_wrapper.get_client_and_model')
    @patch('openai_wrapper.get_instant_context')
    def test_chat_oneshot_cascade(self, mock_gic, mock_get_client):
        mock_gic.return_value = "ctx"
        mock_fail = MagicMock()
        mock_fail.chat.completions.create.side_effect = Exception("Error 1")
        mock_fail2 = MagicMock()
        mock_fail2.chat.completions.create.side_effect = Exception("Error 2")
        mock_success = MagicMock()
        mock_success.chat.completions.create.return_value.choices = [MagicMock(message=MagicMock(content="success cascade"))]
        
        mock_get_client.side_effect = [
            (mock_fail, "model1"),
            (mock_fail2, "model2"),
            (mock_success, "model3")
        ]
        
        openai_wrapper.chat_oneshot("google/gemma-4-31b-it:free", "hello")
        self.assertTrue(mock_success.chat.completions.create.called)

    # 18. chat_oneshot with 'smart'
    @patch('openai_wrapper.smart_route')
    @patch('openai_wrapper.get_client_and_model')
    @patch('openai_wrapper.get_instant_context')
    def test_chat_oneshot_smart(self, mock_gic, mock_get_client, mock_smart_route):
        mock_gic.return_value = ""
        mock_smart_route.return_value = ("nvidia/nemotron-3-super-120b-a12b:free", "role")
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value.choices = [MagicMock(message=MagicMock(content="smart routed!"))]
        mock_get_client.return_value = (mock_client, "nvidia/nemotron-3-super-120b-a12b:free")
        
        openai_wrapper.chat_oneshot("smart", "math")
        self.assertTrue(mock_client.chat.completions.create.called)
        mock_smart_route.assert_called_with("math")

    # 19. chat_oneshot omits temperature for NO_TEMPERATURE_MODELS
    @patch('openai_wrapper.get_client_and_model')
    @patch('openai_wrapper.get_instant_context')
    def test_chat_oneshot_no_temp(self, mock_gic, mock_get_client):
        mock_gic.return_value = ""
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value.choices = [MagicMock(message=MagicMock(content="ok"))]
        mock_get_client.return_value = (mock_client, "o3-mini")
        
        openai_wrapper.chat_oneshot("o3-mini", "hello")
        kwargs = mock_client.chat.completions.create.call_args[1]
        self.assertNotIn("temperature", kwargs)

    # 20. chat_oneshot injects extra_body for deepseek-v4-flash
    @patch('openai_wrapper.get_client_and_model')
    @patch('openai_wrapper.get_instant_context')
    def test_chat_oneshot_extra_body_deepseek(self, mock_gic, mock_get_client):
        mock_gic.return_value = ""
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value.choices = [MagicMock(message=MagicMock(content="ok"))]
        mock_get_client.return_value = (mock_client, "deepseek-ai/deepseek-v4-flash")
        
        openai_wrapper.chat_oneshot("deepseek-ai/deepseek-v4-flash", "hello")
        kwargs = mock_client.chat.completions.create.call_args[1]
        self.assertIn("extra_body", kwargs)
        self.assertTrue(kwargs["extra_body"]["chat_template_kwargs"].get("thinking"))

    # 21. chat_oneshot injects extra_body for nemotron-3-ultra
    @patch('openai_wrapper.get_client_and_model')
    @patch('openai_wrapper.get_instant_context')
    def test_chat_oneshot_extra_body_nemotron(self, mock_gic, mock_get_client):
        mock_gic.return_value = ""
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value.choices = [MagicMock(message=MagicMock(content="ok"))]
        mock_get_client.return_value = (mock_client, "nvidia/nemotron-3-ultra-550b-a55b")
        
        openai_wrapper.chat_oneshot("nvidia/nemotron-3-ultra-550b-a55b", "hello")
        kwargs = mock_client.chat.completions.create.call_args[1]
        self.assertIn("extra_body", kwargs)
        self.assertEqual(kwargs["extra_body"].get("reasoning_budget"), 4096)

    # 28. save_temp_memory handles permissions safely
    @patch('builtins.open', side_effect=PermissionError("Read Only"))
    def test_save_temp_memory_permission(self, mock_open_func):
        try:
            openai_wrapper.save_temp_memory([{"test":"ok"}])
            crashed = False
        except Exception:
            crashed = True
        self.assertFalse(crashed)
        
    # 29. compress_context triggers
    @patch('openai_wrapper.get_client_and_model')
    def test_compress_context_trigger(self, mock_get_client):
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value.choices = [MagicMock(message=MagicMock(content="compressed"))]
        mock_get_client.return_value = (mock_client, "model")
        
        msgs = [{"role": "user", "content": str(i)} for i in range(7)]
        res = openai_wrapper.compress_context(msgs)
        self.assertEqual(len(res), 5)
        self.assertIn("compressed", res[1]["content"])
        
    # 30. get_client_and_model prefix stripping
    @patch('openai_wrapper.os.getenv')
    def test_get_client_and_model_prefix(self, mock_getenv):
        mock_getenv.return_value = "test_key"
        client, m_id = get_client_and_model("qwen/qwen3-coder:free")
        self.assertEqual(m_id, "qwen/qwen3-coder:free")

    # 31. smart_route routes critically audit to council
    def test_smart_route_council(self):
        model, role = smart_route("Please critically audit this plan and give feedback")
        self.assertEqual(model, "council")
        self.assertEqual(role, "llm_council_deliberation")

    # 32. run_council execution and querying stages (offline fallback test)
    @patch('urllib.request.urlopen')
    @patch('openai_wrapper._query_model')
    @patch('openai_wrapper.get_client_and_model')
    def test_run_council(self, mock_get_client, mock_query_model, mock_urlopen):
        mock_urlopen.side_effect = Exception("Fetch failed")
        mock_client = MagicMock()
        mock_get_client.return_value = (mock_client, "google/gemma-4-31b-it:free")
        mock_chunk = MagicMock()
        mock_chunk.choices = [MagicMock(delta=MagicMock(content="Synthesized Answer", reasoning_content=None))]
        mock_client.chat.completions.create.return_value = [mock_chunk]
        
        mock_query_model.side_effect = [
            "Opinion 1", "Opinion 2", "Opinion 3",
            "Review 1", "Review 2", "Review 3"
        ]
        
        reply = openai_wrapper.run_council("Deliberate on microservices tradeoffs")
        self.assertEqual(reply, "Synthesized Answer")
        self.assertEqual(mock_query_model.call_count, 6)

    # 33. run_council selects reasoning Chairman for complex logic (offline fallback test)
    @patch('urllib.request.urlopen')
    @patch('openai_wrapper._query_model')
    @patch('openai_wrapper.get_client_and_model')
    def test_run_council_reasoning(self, mock_get_client, mock_query_model, mock_urlopen):
        mock_urlopen.side_effect = Exception("Fetch failed")
        mock_client = MagicMock()
        mock_get_client.return_value = (mock_client, "openai/o3-mini")
        mock_chunk = MagicMock()
        mock_chunk.choices = [MagicMock(delta=MagicMock(content="Reasoned Answer", reasoning_content="thinking"))]
        mock_client.chat.completions.create.return_value = [mock_chunk]
        
        mock_query_model.side_effect = [
            "Opinion 1", "Opinion 2", "Opinion 3",
            "Review 1", "Review 2", "Review 3"
        ]
        
        reply = openai_wrapper.run_council("Step-by-step math proof for 2+2=4")
        self.assertEqual(reply, "Reasoned Answer")
        mock_get_client.assert_called_with("openai/o3-mini")

    # 34. run_council dynamic model selection with mock registry data
    @patch('urllib.request.urlopen')
    @patch('openai_wrapper._query_model')
    @patch('openai_wrapper.get_client_and_model')
    def test_run_council_dynamic_selection(self, mock_get_client, mock_query_model, mock_urlopen):
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({
            "data": [
                {
                    "id": "qwen/qwen3-max-thinking",
                    "name": "Qwen3 Max Thinking",
                    "created": 1770000000,
                    "pricing": {"prompt": "0.0000008", "completion": "0.000004"},
                    "context_length": 262144,
                    "supported_parameters": ["reasoning", "structured_outputs"]
                },
                {
                    "id": "openai/o3-mini",
                    "name": "OpenAI o3-mini",
                    "created": 1738000000,
                    "pricing": {"prompt": "0.0000011", "completion": "0.0000044"},
                    "context_length": 200000,
                    "supported_parameters": ["reasoning", "structured_outputs"]
                }
            ]
        }).encode('utf-8')
        mock_urlopen.return_value.__enter__.return_value = mock_response

        mock_client = MagicMock()
        mock_get_client.return_value = (mock_client, "qwen/qwen3-max-thinking")
        mock_chunk = MagicMock()
        mock_chunk.choices = [MagicMock(delta=MagicMock(content="Dynamic Synthesized Answer", reasoning_content=None))]
        mock_client.chat.completions.create.return_value = [mock_chunk]

        mock_query_model.side_effect = [
            "Opinion 1", "Opinion 2", "Opinion 3",
            "Review 1", "Review 2", "Review 3"
        ]

        reply = openai_wrapper.run_council("Step-by-step math proof for 2+2=4")
        self.assertEqual(reply, "Dynamic Synthesized Answer")
        mock_get_client.assert_called_with("qwen/qwen3-max-thinking")

    # 29. Test _query_model robust None checks
    @patch('openai_wrapper.get_client_and_model')
    def test_query_model_none_checks(self, mock_get_client):
        mock_client = MagicMock()
        mock_get_client.return_value = (mock_client, "some-model")
        
        # Test resp is None
        mock_client.chat.completions.create.return_value = None
        with self.assertRaises(RuntimeError) as ctx:
            openai_wrapper._query_model("some-model", [{"role": "user", "content": "hi"}])
        self.assertIn("OpenRouter returned None response.", str(ctx.exception))
        
        # Test choices is None
        mock_resp = MagicMock()
        mock_resp.choices = None
        mock_client.chat.completions.create.return_value = mock_resp
        with self.assertRaises(RuntimeError) as ctx:
            openai_wrapper._query_model("some-model", [{"role": "user", "content": "hi"}])
        self.assertIn("OpenRouter response choices field is None.", str(ctx.exception))
        
        # Test choices list is empty
        mock_resp.choices = []
        with self.assertRaises(RuntimeError) as ctx:
            openai_wrapper._query_model("some-model", [{"role": "user", "content": "hi"}])
        self.assertIn("OpenRouter response choices list is empty.", str(ctx.exception))

    # 30. Test _query_model_with_fallback_and_timing
    @patch('openai_wrapper._query_model')
    def test_query_model_with_fallback_and_timing(self, mock_query):
        # First query fails, second succeeds
        mock_query.side_effect = [Exception("Rate limit 429"), "Fallback Success Content"]
        
        attempted_model = "primary-model"
        messages = [{"role": "user", "content": "hi"}]
        excluded = {"primary-model"}
        
        succeeded_model, content, err, elapsed, failed_attempts = openai_wrapper._query_model_with_fallback_and_timing(
            attempted_model, messages, excluded_models=excluded
        )
        
        # Succeeded model should be the first one in the standard fallback pool
        self.assertEqual(succeeded_model, "google/gemma-4-31b-it:free")
        self.assertEqual(content, "Fallback Success Content")
        self.assertIsNone(err)
        self.assertEqual(len(failed_attempts), 1)
        self.assertEqual(failed_attempts[0][0], "primary-model")
        self.assertIn("Rate limit 429", failed_attempts[0][1])

if __name__ == '__main__':
    unittest.main()
