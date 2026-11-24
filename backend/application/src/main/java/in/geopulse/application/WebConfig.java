package in.geopulse.application;
import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.simp.config.MessageBrokerRegistry;
import org.springframework.web.socket.config.annotation.*;
@Configuration
@EnableWebSocketMessageBroker
public class WebConfig implements WebSocketMessageBrokerConfigurer {
    @Override public void configureMessageBroker(MessageBrokerRegistry config){config.enableSimpleBroker("/topic");config.setPreservePublishOrder(true);}
    @Override public void registerStompEndpoints(StompEndpointRegistry registry){registry.addEndpoint("/ws").setAllowedOrigins("http://localhost:5173","http://127.0.0.1:5173","http://localhost:8080","http://127.0.0.1:8080");}
}
