# cd mcp
## run
  pip install -r requirements.txt

# set up
  * check mcp working: http://localhost:3333/health
  * Cấu hình kết nối bên trong Odoo
    Odoo cần biết địa chỉ để gọi đến server MCP. Bạn cần thực hiện cấu hình này một lần duy nhất:
    - Kích hoạt Developer Mode (Thiết lập -> Kích hoạt chế độ nhà phát triển).
    - Truy cập menu Thiết lập (Settings) -> Kỹ thuật (Technical) -> Tham số hệ thống (System Parameters).
    - Nhấn Mới (New) để thêm cấu hình:
      Key: mcp.server.url
      Value: http://localhost:3333/chat (Nếu Odoo và MCP chạy trên cùng một máy).
  * odoo -> apps
    Find odoo_ai_assistant => push Upgrade
