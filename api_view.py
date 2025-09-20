# views.py（續）
from django.http import StreamingHttpResponse
from django.views.decorators.http import require_GET
from django.utils.encoding import smart_str
from langchain_core.messages import SystemMessage, HumanMessage

@require_GET
def chat_stream(request):
    # SSE 建議用 GET；query 透過 ?q= 帶入
    query = request.GET.get("q", "")
    llm = get_llm()

    def event_stream():
        messages = [
            SystemMessage(content="You are a helpful MTBOPS assistant."),
            HumanMessage(content=query),
        ]
        # 使用 LangChain 的 stream()，我們的 MicronChatModel 會做「模擬串流」
        for chunk in llm.stream(messages):
            # chunk 是 AIMessageChunk；取 content
            text_piece = smart_str(chunk.content or "")
            if not text_piece:
                continue
            yield f"data: {text_piece}\n\n"  # 標準 SSE 格式
        # 告訴前端結束
        yield "event: done\ndata: [DONE]\n\n"

    resp = StreamingHttpResponse(event_stream(), content_type="text/event-stream")
    resp["Cache-Control"] = "no-cache"
    resp["X-Accel-Buffering"] = "no"  # 若前面有 Nginx/Ingress，建議關閉緩衝
    return resp
