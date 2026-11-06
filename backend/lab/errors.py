from fastapi.responses import JSONResponse

def error(code, message, status):
    return JSONResponse(status_code=status, content={"error": {"code": code, "message": message}})
